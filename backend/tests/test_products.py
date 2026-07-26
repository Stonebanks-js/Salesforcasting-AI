from tests.conftest import TEST_USER


def _seed_products(fake_db):
    fake_db.seed("products", [
        {"user_id": TEST_USER, "sku": "MUG-001", "product_name": "Ceramic Mug",
         "category": "kitchenware", "sales_days": 120, "last_sale_date": "2026-07-20"},
        {"user_id": TEST_USER, "sku": "TSH-022", "product_name": "Logo Tee",
         "category": "apparel", "sales_days": 90, "last_sale_date": "2026-07-19"},
        {"user_id": "someone-else", "sku": "XXX-000", "product_name": "Not Yours",
         "category": "misc", "sales_days": 5, "last_sale_date": "2026-01-01"},
    ])


def test_products_are_tenant_scoped(onboarded_client, auth_headers, fake_db):
    _seed_products(fake_db)
    resp = onboarded_client.get("/api/v1/products", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # other user's product invisible
    assert {i["sku"] for i in body["items"]} == {"MUG-001", "TSH-022"}


def test_products_search(onboarded_client, auth_headers, fake_db):
    _seed_products(fake_db)
    resp = onboarded_client.get("/api/v1/products?search=mug", headers=auth_headers)
    assert [i["sku"] for i in resp.json()["items"]] == ["MUG-001"]


def test_products_has_forecast_flag(onboarded_client, auth_headers, fake_db):
    _seed_products(fake_db)
    fake_db.seed("forecasts", [{
        "user_id": TEST_USER, "sku": "MUG-001", "forecast_date": "2026-07-27",
        "model_run_id": "run-1", "model_version": "lightgbm:1",
        "yhat": 10, "yhat_lower": 8, "yhat_upper": 12, "mape_backtest": 15.0,
        "generated_at": "2026-07-26T06:00:00Z",
    }])
    resp = onboarded_client.get("/api/v1/products", headers=auth_headers)
    flags = {i["sku"]: i["has_forecast"] for i in resp.json()["items"]}
    assert flags == {"MUG-001": True, "TSH-022": False}


def test_sales_history_endpoint(onboarded_client, auth_headers, fake_db):
    fake_db.seed("sales_daily", [
        {"user_id": TEST_USER, "sku": "MUG-001", "date": "2026-07-01", "quantity": 5,
         "revenue": 60.0, "promo_flag": False},
        {"user_id": TEST_USER, "sku": "MUG-001", "date": "2026-07-02", "quantity": 7,
         "revenue": 84.0, "promo_flag": True},
    ])
    resp = onboarded_client.get("/api/v1/sales?sku=MUG-001", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [i["date"] for i in items] == ["2026-07-01", "2026-07-02"]


def test_sales_history_404_for_unknown_sku(onboarded_client, auth_headers):
    resp = onboarded_client.get("/api/v1/sales?sku=NOPE", headers=auth_headers)
    assert resp.status_code == 404
