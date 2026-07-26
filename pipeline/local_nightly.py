"""Serverless nightly pipeline (Phase 15, decision 027).

Replaces the Spark/Delta path at pilot scale: reads sales + signal envelopes
from Supabase, runs the SAME unit-tested pure transforms and ML code, and
upserts forecasts back into the serving tables. No JVM, no broker, no VM —
runs on a GitHub Actions runner in a few minutes.

Spark/Delta jobs remain in the repo as the v2 scale-up path.
"""
import logging
import os
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ml.infer import build_future_context, infer_all, load_chosen_models
from ml.train import train_all
from transforms.calendar_signals import build_calendar_daily
from transforms.features import build_feature_rows
from transforms.sales import to_silver
from transforms.signals_daily import events_to_daily

logger = logging.getLogger("local_nightly")

PAGE = 1000
FORECAST_RUN_RETENTION_DAYS = 7
SIGNAL_LOOKBACK_DAYS = 400
HORIZON = 30


def paginate(query_factory, page_size: int = PAGE) -> list[dict]:
    """Fetch all rows via PostgREST range pagination (default cap is 1000)."""
    rows: list[dict] = []
    offset = 0
    while True:
        resp = query_factory().range(offset, offset + page_size - 1).execute()
        rows.extend(resp.data)
        if len(resp.data) < page_size:
            return rows
        offset += page_size


def load_inputs(client) -> dict:
    sales = paginate(lambda: client.table("sales_daily").select("*"))
    events = paginate(
        lambda: client.table("signal_events").select("source,entity_key,observed_at,payload,ingested_at")
        .gte("observed_at", (date.today() - timedelta(days=SIGNAL_LOOKBACK_DAYS)).isoformat())
    )
    profiles = paginate(lambda: client.table("profiles").select("id,country_code,timezone"))
    calendar_events = paginate(lambda: client.table("calendar_events").select("user_id,label,start_date,end_date"))
    return {"sales": sales, "events": events, "profiles": profiles,
            "calendar_events": calendar_events}


def organize_signals(events: list[dict]) -> dict:
    """Split signal_event rows into per-source lookup structures."""
    weather: dict[str, dict[str, dict]] = defaultdict(dict)   # user -> date -> payload
    trends: dict[str, dict[str, dict]] = defaultdict(dict)
    holidays: dict[str, set] = defaultdict(set)               # country -> {dates}
    flat_events: list[dict] = []                              # for events_to_daily
    macro_points: list[dict] = []

    for row in events:
        source, payload = row["source"], row["payload"]
        day = row["observed_at"]
        if source == "weather":
            weather[payload.get("user_id", "")][day] = payload
        elif source == "trends":
            trends[payload.get("user_id", "")][day] = payload
        elif source == "holidays":
            holidays[payload.get("country_code", "")].add(day)
        elif source == "events":
            flat_events.append({"date": day, **payload})
        elif source == "macro":
            macro_points.append({"series": payload.get("series"), "date": day,
                                 "value": payload.get("value")})
    return {"weather": weather, "trends": trends, "holidays": holidays,
            "events": flat_events, "macro": macro_points}


def run_nightly(client, model_dir: str | None = None) -> dict:
    """Full nightly run. Returns a summary dict (also logged)."""
    model_dir = model_dir or tempfile.mkdtemp(prefix="trendcast-models-")
    inputs = load_inputs(client)
    sales, profiles = inputs["sales"], inputs["profiles"]
    signals = organize_signals(inputs["events"])
    logger.info("loaded %d sales rows, %d signal events, %d profiles",
                len(sales), len(inputs["events"]), len(profiles))
    if not sales or not profiles:
        logger.info("nothing to do")
        return {"status": "empty", "forecasts": 0}

    country_by_user = {p["id"]: p.get("country_code", "") for p in profiles}
    breaks_by_user: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ev in inputs["calendar_events"]:
        breaks_by_user[ev["user_id"]].append((ev["start_date"], ev["end_date"]))

    silver_sales = to_silver(sales)
    sales_by_user_sku: dict[tuple, list[dict]] = defaultdict(list)
    for r in silver_sales:
        sales_by_user_sku[(r["user_id"], r["sku"])].append(r)

    events_daily = events_to_daily(signals["events"])
    events_by_user: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in events_daily:
        events_by_user[row["user_id"]][row["date"]] = row

    today = date.today()
    feature_rows: list[dict] = []
    for (user_id, sku), rows in sales_by_user_sku.items():
        dates = [r["date"] for r in rows]
        calendar_rows = build_calendar_daily(
            user_id, date.fromisoformat(min(dates)),
            today + timedelta(days=HORIZON),
            holiday_dates=signals["holidays"].get(country_by_user.get(user_id, ""), set()),
            school_breaks=breaks_by_user.get(user_id, []),
        )
        feature_rows.extend(build_feature_rows(
            rows,
            weather_by_date=signals["weather"].get(user_id, {}),
            calendar_by_date={r["date"]: r for r in calendar_rows},
            trends_by_date=signals["trends"].get(user_id, {}),
            events_by_date=events_by_user.get(user_id, {}),
        ))
    logger.info("built %d feature rows for %d SKUs", len(feature_rows),
                len(sales_by_user_sku))

    # Train + select + persist artifacts (ephemeral; retrained nightly).
    metrics = train_all(feature_rows, model_dir=model_dir)
    models = load_chosen_models(metrics, model_dir=model_dir)

    history = {k: [float(r["quantity"]) for r in sorted(v, key=lambda x: x["date"])]
               for k, v in sales_by_user_sku.items()}

    start = today + timedelta(days=1)
    weather_rows = [{**p, "user_id": u, "date": d}
                    for u, by_date in signals["weather"].items()
                    for d, p in by_date.items()]
    trends_rows = [dict(user_id=u, date=d, interest=p.get("interest"))
                   for u, by_date in signals["trends"].items()
                   for d, p in by_date.items()]
    # Calendar is deterministic: rebuild per user for the future window.
    calendar_rows_all: list[dict] = []
    for user_id in {p["id"] for p in profiles}:
        calendar_rows_all.extend(build_calendar_daily(
            user_id, start, start + timedelta(days=HORIZON - 1),
            holiday_dates=signals["holidays"].get(country_by_user.get(user_id, ""), set()),
            school_breaks=breaks_by_user.get(user_id, []),
        ))
    context = build_future_context(
        calendar_rows_all, weather_rows, events_daily, trends_rows, start, HORIZON,
    )

    batch_id = f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    forecasts, factors = infer_all(models, history, context, start,
                                   horizon=HORIZON, batch_run_id=batch_id)
    logger.info("inferred %d forecast rows, %d factor rows", len(forecasts), len(factors))

    _upsert_batches(client, "forecasts", forecasts,
                    "user_id,sku,forecast_date,model_run_id")
    _upsert_batches(client, "forecast_factors", factors,
                    "user_id,sku,model_run_id,factor")
    _prune_old_runs(client)
    return {"status": "ok", "skus": len(sales_by_user_sku),
            "forecasts": len(forecasts), "factors": len(factors),
            "batch": batch_id}


def _upsert_batches(client, table: str, rows: list[dict], on_conflict: str) -> None:
    for i in range(0, len(rows), 500):
        client.table(table).upsert(rows[i : i + 500], on_conflict=on_conflict).execute()


def _prune_old_runs(client) -> None:
    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=FORECAST_RUN_RETENTION_DAYS)
    try:
        # forecasts pruned by timestamp; factors by batch id (nightly-YYYYMMDD
        # sorts lexicographically by run date).
        client.table("forecasts").delete().lt("generated_at", cutoff_dt.isoformat()).execute()
        client.table("forecast_factors").delete().lt(
            "model_run_id", f"nightly-{cutoff_dt.strftime('%Y%m%d')}"
        ).execute()
        client.table("signal_events").delete().lt(
            "ingested_at", (datetime.now(timezone.utc)
                            - timedelta(days=SIGNAL_LOOKBACK_DAYS)).isoformat()
        ).execute()
    except Exception:  # noqa: BLE001 - pruning must never fail the run
        logger.warning("prune failed", exc_info=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not configured")
    from supabase import create_client

    summary = run_nightly(create_client(url, key))
    logger.info("nightly complete: %s", summary)


if __name__ == "__main__":
    main()
