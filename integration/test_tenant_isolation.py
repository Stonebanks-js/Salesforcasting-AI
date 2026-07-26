"""Tenant isolation: user B must never see user A's data through any endpoint.

(Unit tests mock RLS; these tests verify the API layer *always* scopes queries
by the JWT-derived user_id — the second line of defense after Postgres RLS.)
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.kafka import get_producer
from app.main import create_app
from tests.fakes import FakeDb, FakeProducer

from helpers import mint_token

USER_A, USER_B = "user-aaa", "user-bbb"


@pytest.fixture
def clients():
    db = FakeDb()
    db.seed("profiles", [
        {"id": USER_A, "country_code": "US", "onboarding_complete": True},
        {"id": USER_B, "country_code": "US", "onboarding_complete": True},
    ])
    db.seed("products", [
        {"user_id": USER_A, "sku": "A-SKU", "product_name": "A's product",
         "sales_days": 100, "last_sale_date": "2026-07-20"},
    ])
    db.seed("sales_daily", [
        {"user_id": USER_A, "sku": "A-SKU", "date": "2026-07-20",
         "quantity": 5, "revenue": 50, "promo_flag": False},
    ])
    db.seed("forecasts", [
        {"user_id": USER_A, "sku": "A-SKU", "forecast_date": "2026-07-27",
         "model_run_id": "nightly-1", "model_version": "lightgbm:x",
         "yhat": 10, "yhat_lower": 8, "yhat_upper": 12, "mape_backtest": 12.0,
         "generated_at": "2026-07-26T06:00:00Z"},
    ])
    db.seed("uploads", [
        {"id": "upl-a", "user_id": USER_A, "kind": "sales",
         "file_path": f"{USER_A}/f.csv", "status": "loaded", "row_count": 1,
         "created_at": "2026-07-26T00:00:00Z"},
    ])
    db.seed("tracked_asins", [{"user_id": USER_A, "asin": "B08AAAAAA1"}])
    db.seed("calendar_events", [
        {"id": 1, "user_id": USER_A, "label": "A's break",
         "start_date": "2026-08-01", "end_date": "2026-08-10"},
    ])

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_producer] = lambda: FakeProducer()
    app.state.limiter.enabled = False
    client = TestClient(app)
    headers_b = {"Authorization": f"Bearer {mint_token(USER_B)}"}
    return client, headers_b


def test_b_sees_no_products(clients):
    client, headers_b = clients
    resp = client.get("/api/v1/products", headers=headers_b)
    assert resp.json()["total"] == 0


def test_b_cannot_read_a_sales(clients):
    client, headers_b = clients
    resp = client.get("/api/v1/sales?sku=A-SKU", headers=headers_b)
    assert resp.status_code == 404


def test_b_cannot_read_a_forecasts(clients):
    client, headers_b = clients
    resp = client.get("/api/v1/forecasts?skus=A-SKU", headers=headers_b)
    assert resp.status_code == 404  # sku_not_found for B, not a leak


def test_b_cannot_read_a_upload(clients):
    client, headers_b = clients
    resp = client.get("/api/v1/uploads/upl-a", headers=headers_b)
    assert resp.status_code == 404


def test_b_sees_no_asins_or_calendar(clients):
    client, headers_b = clients
    assert client.get("/api/v1/marketplace/asins", headers=headers_b).json()["items"] == []
    assert client.get("/api/v1/calendar/events", headers=headers_b).json()["items"] == []


def test_b_cannot_delete_a_calendar_event(clients):
    client, headers_b = clients
    resp = client.delete("/api/v1/calendar/events/1", headers=headers_b)
    assert resp.status_code == 404  # delete scoped to B finds nothing
