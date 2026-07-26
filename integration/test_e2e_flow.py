"""End-to-end seam test: CSV upload -> Kafka events -> Silver -> Gold ->
train -> infer -> publish (into serving tables) -> API -> frontend contract.

Every stage uses the REAL production code path; only IO boundaries (DB,
broker, Spark) are faked — which is exactly what the container wiring does.
"""
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.kafka import get_producer
from app.main import create_app
from app.services.csv_sales import load_sales_upload
from ml.infer import build_future_context, infer_all, load_chosen_models
from ml.train import train_all
from tests.fakes import FakeDb, FakeProducer
from transforms.calendar_signals import build_calendar_daily
from transforms.features import build_feature_rows
from transforms.sales import to_silver

from helpers import USER, synth_csv, trends_lookup, weather_lookup

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def e2e(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    db, producer = FakeDb(), FakeProducer()

    # --- Stage 1: backend CSV validation + load (real service code) ---------
    content = synth_csv(days=200)
    load_sales_upload(db, producer, user_id=USER, upload_id="upl-1",
                      content=content, max_rows=100_000, max_skus=500)
    assert len(db.tables["products"]) == 2
    assert len(producer.events) == 400  # 2 SKUs x 200 days

    # --- Stage 2: Kafka envelopes -> bronze payloads -> silver --------------
    bronze_payloads = []
    for _topic, _key, envelope in producer.events:
        payload = dict(envelope["payload"])
        payload["ingested_at"] = envelope["ingested_at"]
        bronze_payloads.append(payload)
    silver_sales = to_silver(bronze_payloads)
    assert len(silver_sales) == 400

    # --- Stage 3: silver signals + gold features ----------------------------
    sales_dates = [r["date"] for r in silver_sales]
    span_start = date.fromisoformat(min(sales_dates))
    span_end = date.fromisoformat(max(sales_dates)) + timedelta(days=30)
    calendar_rows = build_calendar_daily(
        USER, span_start, span_end,
        holiday_dates={(date.today() + timedelta(days=10)).isoformat()},
        school_breaks=[],
    )
    calendar_by_date = {r["date"]: r for r in calendar_rows}
    weather_by_date = weather_lookup()
    trends_by_date = trends_lookup()

    feature_rows = []
    for sku in ("MUG-001", "TSH-022"):
        sku_sales = [r for r in silver_sales if r["sku"] == sku]
        feature_rows.extend(build_feature_rows(
            sku_sales,
            weather_by_date=weather_by_date,
            calendar_by_date=calendar_by_date,
            trends_by_date=trends_by_date,
        ))
    assert len(feature_rows) == 400

    # --- Stage 4: train (real LightGBM) + select ---------------------------
    metrics = train_all(feature_rows, model_dir=str(tmp / "models"))
    assert len(metrics) == 2
    assert all(m["chosen"] in ("lightgbm", "seasonal-naive") for m in metrics)

    # --- Stage 5: batch inference with future context -----------------------
    models = load_chosen_models(metrics, model_dir=str(tmp / "models"))
    history = {}
    for sku in ("MUG-001", "TSH-022"):
        history[(USER, sku)] = [
            float(r["quantity"])
            for r in sorted(silver_sales, key=lambda x: x["date"]) if r["sku"] == sku
        ]
    start = date.today() + timedelta(days=1)
    context = build_future_context(
        calendar_rows, [dict(user_id=USER, date=d, **w) for d, w in weather_by_date.items()],
        [], [dict(user_id=USER, date=d, interest=v["interest"]) for d, v in trends_by_date.items()],
        start, 30,
    )
    forecasts, factors = infer_all(models, history, context, start, horizon=30)
    assert len(forecasts) == 60  # 2 SKUs x 30 days

    # --- Stage 6: publish into serving tables + serve via real API ---------
    db.seed("forecasts", forecasts)
    db.seed("forecast_factors", factors)
    db.seed("signal_status", [
        {"signal": s, "status": "live" if s != "trends" else "stale",
         "last_success_at": "2026-07-26T05:00:00Z", "calls_today": 1}
        for s in ("weather", "holidays", "trends", "macro", "events", "marketplace")
    ])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_producer] = lambda: producer
    app.state.limiter.enabled = False
    client = TestClient(app)

    from helpers import mint_token
    headers = {"Authorization": f"Bearer {mint_token(USER)}"}
    resp = client.get("/api/v1/forecasts?skus=MUG-001,TSH-022&horizon=30",
                      headers=headers)
    assert resp.status_code == 200, resp.json()
    return resp.json(), metrics


def test_e2e_forecast_quality(e2e):
    body, metrics = e2e
    for m in metrics:
        assert m["mape"] is None or m["mape"] <= 40.0, \
            f"{m['sku']} MAPE {m['mape']} exceeds the pilot success bound"
    for s in body["series"]:
        assert len(s["points"]) == 30
        for p in s["points"]:
            assert p["yhat_lower"] <= p["yhat"] <= p["yhat_upper"]


def test_e2e_degradation_visible(e2e):
    body, _ = e2e
    # trends is stale -> every series flagged degraded, still served (NFR-3).
    assert all(s["degraded"] for s in body["series"])
    health = {h["signal"]: h["status"] for h in body["signal_health"]}
    assert health["trends"] == "stale" and health["weather"] == "live"


def _ts_interface_fields(name: str) -> set[str]:
    """Extract field names from a TypeScript interface in frontend types.ts —
    guards frontend/backend contract drift."""
    text = (ROOT / "frontend" / "src" / "lib" / "types.ts").read_text()
    block = re.search(rf"export interface {name} {{(.*?)}}", text, re.S)
    assert block, f"interface {name} not found in types.ts"
    return set(re.findall(r"^\s*(\w+)\??:", block.group(1), re.M))


def test_e2e_response_matches_frontend_contract(e2e):
    body, _ = e2e
    assert _ts_interface_fields("ForecastResponse") <= set(body.keys())

    series = body["series"][0]
    assert _ts_interface_fields("ForecastSeries") <= set(series.keys())
    point = series["points"][0]
    assert _ts_interface_fields("ForecastPoint") <= set(point.keys())
    if series["factors"]:
        assert _ts_interface_fields("Factor") <= set(series["factors"][0].keys())
    health = body["signal_health"][0]
    assert _ts_interface_fields("SignalHealth") <= set(health.keys())
