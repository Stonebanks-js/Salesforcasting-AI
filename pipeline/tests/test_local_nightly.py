"""Serverless nightly (decision 027): Supabase in -> forecasts upserted out.

Exercises the full pure-Python path with fakes: load -> organize -> silver ->
features -> train (real LightGBM) -> infer -> upsert -> prune.
"""
import math
from datetime import date, timedelta

from local_nightly import organize_signals, run_nightly
from tests.fakes import FakeDb

USER = "u1"


def _seed_sales(db: FakeDb, days: int = 150) -> None:
    today = date.today()
    rows = []
    for sku, base in (("MUG-001", 30.0), ("TSH-022", 18.0)):
        for d in range(days, 0, -1):
            day = today - timedelta(days=d)
            qty = max(0.0, base * (1 + 0.3 * math.sin(d / 14)) * (1.2 if day.weekday() >= 5 else 1.0))
            rows.append({"user_id": USER, "sku": sku, "date": day.isoformat(),
                         "quantity": round(qty), "revenue": qty * 10,
                         "price": 10.0, "promo_flag": False, "source": "csv"})
    db.seed("sales_daily", rows)


def _seed_signals(db: FakeDb) -> None:
    today = date.today()
    events = []
    for d in range(60, -30, -1):  # history + 30-day forecast window
        day = (today - timedelta(days=d)).isoformat()
        events.append({"source": "weather", "entity_key": USER, "observed_at": day,
                       "ingested_at": f"{day}T06:00:00Z",
                       "payload": {"user_id": USER, "temp_avg": 22.0, "precip_mm": 1.0}})
        events.append({"source": "trends", "entity_key": f"{USER}:kitchenware",
                       "observed_at": day, "ingested_at": f"{day}T06:00:00Z",
                       "payload": {"user_id": USER, "category": "kitchenware",
                                   "keyword": "mug", "interest": 55}})
    events.append({"source": "holidays", "entity_key": "US:2026-12-25",
                   "observed_at": "2026-12-25", "ingested_at": "2026-01-01T00:00:00Z",
                   "payload": {"country_code": "US", "local_name": "Christmas"}})
    db.seed("signal_events", events)


def test_organize_signals():
    signals = organize_signals([
        {"source": "weather", "entity_key": "u1", "observed_at": "2026-07-26",
         "payload": {"user_id": "u1", "temp_avg": 25.0}},
        {"source": "holidays", "entity_key": "US:2026-12-25", "observed_at": "2026-12-25",
         "payload": {"country_code": "US"}},
        {"source": "events", "entity_key": "u1:E1", "observed_at": "2026-08-01",
         "payload": {"user_id": "u1", "large_venue": True, "category": "Music"}},
    ])
    assert signals["weather"]["u1"]["2026-07-26"]["temp_avg"] == 25.0
    assert "2026-12-25" in signals["holidays"]["US"]
    assert signals["events"][0]["large_venue"] is True


def test_run_nightly_end_to_end(tmp_path):
    db = FakeDb()
    db.seed("profiles", [{"id": USER, "country_code": "US",
                          "timezone": "America/Chicago"}])
    _seed_sales(db)
    _seed_signals(db)

    summary = run_nightly(db, model_dir=str(tmp_path / "models"))

    assert summary["status"] == "ok"
    assert summary["skus"] == 2
    assert summary["forecasts"] == 60  # 2 SKUs x 30 days
    assert summary["batch"].startswith("nightly-")

    forecasts = db.tables["forecasts"]
    assert len(forecasts) == 60
    assert all(f["user_id"] == USER for f in forecasts)
    assert all(f["yhat_lower"] <= f["yhat"] <= f["yhat_upper"] for f in forecasts)
    # Factors were written for SKUs whose model produced them.
    assert "forecast_factors" in db.tables


def test_run_nightly_empty_inputs(tmp_path):
    db = FakeDb()
    db.seed("profiles", [{"id": USER, "country_code": "US", "timezone": "UTC"}])
    summary = run_nightly(db, model_dir=str(tmp_path))
    assert summary["status"] == "empty"
    assert "forecasts" not in db.tables
