"""Batch inference job: latest trained models + future exogenous context ->
gold_forecasts + gold_forecast_factors (published to Supabase by the
publish_to_supabase job).
"""
import json
import os
import pickle
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ml.forecaster import forecast_with_model

MODEL_DIR = os.environ.get("MODEL_DIR", "/opt/models")
DEFAULT_HORIZON = 30


def load_chosen_models(metrics_rows: list[dict], model_dir: str = MODEL_DIR) -> dict:
    """(user_id, sku) -> {chosen, model|None, model_run_id, model_version,
    mape_backtest, factors} from the latest training run per SKU."""
    latest: dict[tuple, dict] = {}
    for m in sorted(metrics_rows, key=lambda r: r["trained_at"]):
        latest[(m["user_id"], m["sku"])] = m

    models = {}
    for key, m in latest.items():
        model = None
        if m["chosen"] == "lightgbm" and m.get("artifact_path"):
            path = m["artifact_path"]
            if not os.path.isabs(path):
                path = os.path.join(model_dir, path)
            try:
                with open(path, "rb") as fh:
                    model = pickle.load(fh)  # noqa: S301 - artifacts are self-produced
            except (OSError, pickle.UnpicklingError):
                model = None  # falls back to baseline at forecast time
        models[key] = {**m, "model": model}
    return models


def build_future_context(
    calendar_rows: list[dict],
    weather_rows: list[dict],
    events_rows: list[dict],
    trends_rows: list[dict],
    start: date,
    horizon: int,
) -> dict[tuple, dict]:
    """(user_id, date_iso) -> exogenous dict for future dates."""
    end = start + timedelta(days=horizon - 1)
    ctx: dict[tuple, dict] = defaultdict(dict)

    def in_range(d: str) -> bool:
        return start.isoformat() <= d <= end.isoformat()

    for r in calendar_rows:
        if in_range(r["date"]):
            ctx[(r["user_id"], r["date"])].update({
                "is_holiday": r.get("is_holiday", False),
                "days_to_holiday": r.get("days_to_holiday"),
                "is_school_break": r.get("is_school_break", False),
            })
    for r in weather_rows:
        if in_range(r["date"]):
            ctx[(r["user_id"], r["date"])].update({
                "temp_avg": r.get("temp_avg"), "precip_mm": r.get("precip_mm"),
            })
    for r in events_rows:
        if in_range(r["date"]):
            ctx[(r["user_id"], r["date"])].update({
                "event_count": r.get("event_count", 0),
                "large_event_count": r.get("large_event_count", 0),
            })
    # Trends: last-known value carried forward (data_sources.md fallback).
    last_by_user: dict[str, float | None] = {}
    for r in sorted(trends_rows, key=lambda x: x["date"]):
        last_by_user[r["user_id"]] = r.get("interest")
    for (user_id, d), bag in ctx.items():
        bag.setdefault("trends_interest", last_by_user.get(user_id))
    return dict(ctx)


def infer_all(
    models: dict,
    history_by_sku: dict[tuple, list[float]],
    context: dict[tuple, dict],
    start: date,
    horizon: int = DEFAULT_HORIZON,
    batch_run_id: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Returns (gold_forecasts rows, gold_forecast_factors rows).

    batch_run_id identifies the NIGHTLY BATCH, not per-SKU MLflow runs — the
    serving layer exposes "the latest run" as one coherent batch
    (api_contracts.md §2.5). Per-SKU MLflow run ids live in gold_model_metrics.
    """
    batch_run_id = batch_run_id or f"nightly-{start.isoformat()}"
    now = datetime.now(timezone.utc).isoformat()
    forecast_rows: list[dict] = []
    factor_rows: list[dict] = []

    for (user_id, sku), entry in sorted(models.items()):
        history = history_by_sku.get((user_id, sku), [])
        if not history:
            continue
        run_id = batch_run_id
        exog = {
            d: ctx for (u, d), ctx in context.items() if u == user_id
        }
        points = forecast_with_model(
            entry["chosen"], entry.get("model"), history, start, horizon, exog,
        )
        for p in points:
            forecast_rows.append({
                "user_id": user_id,
                "sku": sku,
                "forecast_date": p["date"],
                "model_run_id": run_id,
                "model_version": entry["model_version"],
                "yhat": round(p["yhat"], 2),
                "yhat_lower": round(p["yhat_lower"], 2),
                "yhat_upper": round(p["yhat_upper"], 2),
                "mape_backtest": entry.get("mape_backtest"),
                "generated_at": now,
            })
        for f in (entry.get("factors") or [])[:5]:
            factor_rows.append({
                "user_id": user_id, "sku": sku, "model_run_id": run_id,
                "factor": f["factor"], "importance": f["importance"],
                "direction": f["direction"],
            })
    return forecast_rows, factor_rows


def main() -> None:
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from jobs.common import delta_path, get_spark

    spark = get_spark("trendcast-infer")

    def load(table: str) -> list[dict]:
        try:
            return spark.read.format("delta").load(delta_path(table)).toPandas().to_dict("records")
        except Exception:
            return []

    metrics = load("gold_model_metrics")
    features = load("gold_features")
    if not metrics or not features:
        print("[infer] missing inputs; run gold_features + train first")
        return

    history_by_sku: dict[tuple, list[float]] = defaultdict(list)
    for r in sorted(features, key=lambda x: x["date"]):
        history_by_sku[(r["user_id"], r["sku"])].append(float(r["quantity"]))

    models = load_chosen_models(metrics)
    start = date.today() + timedelta(days=1)
    batch_run_id = f"nightly-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    context = build_future_context(
        load("silver_calendar_daily"), load("silver_weather_daily"),
        load("silver_events_daily"), load("silver_trends_daily"),
        start, DEFAULT_HORIZON,
    )
    forecast_rows, factor_rows = infer_all(
        models, dict(history_by_sku), context, start, batch_run_id=batch_run_id
    )

    if forecast_rows:
        spark.createDataFrame(forecast_rows).write.format("delta").mode("overwrite") \
            .save(delta_path("gold_forecasts"))
    if factor_rows:
        spark.createDataFrame(factor_rows).write.format("delta").mode("overwrite") \
            .save(delta_path("gold_forecast_factors"))
    print(f"[infer] wrote {len(forecast_rows)} forecasts, {len(factor_rows)} factors")
    spark.stop()


if __name__ == "__main__":
    main()
