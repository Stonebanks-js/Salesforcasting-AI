"""Forecast serving incl. the degradation contract (NFR-3)."""
from datetime import date, timedelta

from tests.conftest import TEST_USER


def _seed_base(fake_db, sales_days=120):
    fake_db.seed("products", [
        {"user_id": TEST_USER, "sku": "MUG-001", "product_name": "Mug",
         "sales_days": sales_days, "last_sale_date": "2026-07-20"},
        {"user_id": TEST_USER, "sku": "TSH-022", "product_name": "Tee",
         "sales_days": sales_days, "last_sale_date": "2026-07-20"},
    ])


def _seed_run(fake_db, run_id="run-1", model="lightgbm:3"):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    fake_db.seed("forecasts", [
        {"user_id": TEST_USER, "sku": "MUG-001", "forecast_date": tomorrow,
         "model_run_id": run_id, "model_version": model,
         "yhat": 42.0, "yhat_lower": 31.0, "yhat_upper": 55.0,
         "mape_backtest": 14.2, "generated_at": "2026-07-26T06:00:00+00:00"},
        {"user_id": TEST_USER, "sku": "TSH-022", "forecast_date": tomorrow,
         "model_run_id": run_id, "model_version": model,
         "yhat": 10.0, "yhat_lower": 7.0, "yhat_upper": 14.0,
         "mape_backtest": 21.7, "generated_at": "2026-07-26T06:00:00+00:00"},
        # An older run that must NOT be served:
        {"user_id": TEST_USER, "sku": "MUG-001", "forecast_date": tomorrow,
         "model_run_id": "run-0", "model_version": "lightgbm:2",
         "yhat": 99.0, "yhat_lower": 90.0, "yhat_upper": 110.0,
         "mape_backtest": 30.0, "generated_at": "2026-07-25T06:00:00+00:00"},
    ])
    fake_db.seed("forecast_factors", [
        {"user_id": TEST_USER, "sku": "MUG-001", "model_run_id": run_id,
         "factor": "trends_interest", "importance": 0.31, "direction": "up"},
        {"user_id": TEST_USER, "sku": "MUG-001", "model_run_id": run_id,
         "factor": "days_to_holiday", "importance": 0.22, "direction": "up"},
    ])


def _seed_health(fake_db, statuses=None):
    statuses = statuses or {}
    for sig in ("weather", "holidays", "trends", "macro", "events", "marketplace"):
        fake_db.seed("signal_status", [{
            "signal": sig, "status": statuses.get(sig, "live"),
            "last_success_at": "2026-07-26T05:00:00+00:00", "calls_today": 3,
        }])


def test_multi_sku_forecast_happy_path(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    _seed_run(fake_db)
    _seed_health(fake_db)

    resp = onboarded_client.get(
        "/api/v1/forecasts?skus=MUG-001,TSH-022&horizon=30", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_run_id"] == "run-1"
    assert len(body["series"]) == 2

    mug = next(s for s in body["series"] if s["sku"] == "MUG-001")
    assert mug["points"][0]["yhat"] == 42.0  # served from latest run only
    assert mug["degraded"] is False
    assert mug["factors"][0]["factor"] == "trends_interest"
    assert len(body["signal_health"]) == 6


def test_degraded_flag_when_signal_stale(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    _seed_run(fake_db)
    _seed_health(fake_db, statuses={"trends": "stale"})

    body = onboarded_client.get(
        "/api/v1/forecasts?skus=MUG-001", headers=auth_headers
    ).json()
    assert body["series"][0]["degraded"] is True  # flagged, not an error (NFR-3)
    assert body["series"][0]["points"]  # forecast still served


def test_baseline_model_marks_degraded(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    _seed_run(fake_db, model="seasonal-naive")
    _seed_health(fake_db)

    body = onboarded_client.get(
        "/api/v1/forecasts?skus=MUG-001", headers=auth_headers
    ).json()
    assert body["series"][0]["degraded"] is True


def test_unknown_sku_404(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    resp = onboarded_client.get("/api/v1/forecasts?skus=NOPE-1", headers=auth_headers)
    assert resp.status_code == 404
    assert "sku_not_found" in resp.json()["detail"]


def test_insufficient_history_409(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db, sales_days=30)  # below 60-day minimum
    resp = onboarded_client.get("/api/v1/forecasts?skus=MUG-001", headers=auth_headers)
    assert resp.status_code == 409
    assert "insufficient_history" in resp.json()["detail"]


def test_no_run_yet_404(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    resp = onboarded_client.get("/api/v1/forecasts?skus=MUG-001", headers=auth_headers)
    assert resp.status_code == 404
    assert "nightly batch" in resp.json()["detail"]


def test_horizon_validation(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    resp = onboarded_client.get(
        "/api/v1/forecasts?skus=MUG-001&horizon=21", headers=auth_headers
    )
    assert resp.status_code == 400


def test_too_many_skus_rejected(onboarded_client, auth_headers, fake_db):
    _seed_base(fake_db)
    skus = ",".join(f"SKU-{i}" for i in range(11))
    resp = onboarded_client.get(f"/api/v1/forecasts?skus={skus}", headers=auth_headers)
    assert resp.status_code == 400
