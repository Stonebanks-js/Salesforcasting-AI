"""Signal settings/status + Keepa ASIN cap tests."""
from tests.conftest import TEST_USER


# --- signals ---------------------------------------------------------------
def test_get_signal_settings(onboarded_client, auth_headers):
    resp = onboarded_client.get("/api/v1/signals/settings", headers=auth_headers)
    assert resp.status_code == 200
    items = {i["signal"]: i["enabled"] for i in resp.json()["items"]}
    assert items["marketplace"] is False
    assert items["weather"] is True


def test_patch_signal_settings(onboarded_client, auth_headers):
    resp = onboarded_client.patch(
        "/api/v1/signals/settings",
        json={"marketplace": True, "trends": False},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    items = {i["signal"]: i["enabled"] for i in resp.json()["items"]}
    assert items["marketplace"] is True
    assert items["trends"] is False
    assert items["weather"] is True  # untouched


def test_patch_rejects_unknown_signal(onboarded_client, auth_headers):
    resp = onboarded_client.patch(
        "/api/v1/signals/settings", json={"crypto": True}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_signal_status_visible_to_any_authenticated_user(onboarded_client, auth_headers, fake_db):
    fake_db.seed("signal_status", [
        {"signal": "weather", "status": "live",
         "last_success_at": "2026-07-26T05:00:00+00:00", "calls_today": 5},
    ])
    resp = onboarded_client.get("/api/v1/signals/status", headers=auth_headers)
    assert resp.json()["items"][0]["status"] == "live"


# --- marketplace -------------------------------------------------------------
def test_asin_crud_and_cap(onboarded_client, auth_headers):
    # Add up to the cap of 10.
    for i in range(10):
        resp = onboarded_client.post(
            "/api/v1/marketplace/asins",
            json={"asin": f"B08XYZ12{i:02d}"[-10:]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.json()

    listed = onboarded_client.get("/api/v1/marketplace/asins", headers=auth_headers).json()
    assert len(listed["items"]) == 10

    # 11th exceeds the free-tier cap.
    resp = onboarded_client.post(
        "/api/v1/marketplace/asins", json={"asin": "B09ABC4567"}, headers=auth_headers
    )
    assert resp.status_code == 403
    assert "asin_cap_reached" in resp.json()["detail"]

    # Delete frees a slot.
    resp = onboarded_client.delete("/api/v1/marketplace/asins/B08XYZ1200", headers=auth_headers)
    assert resp.status_code == 204
    resp = onboarded_client.post(
        "/api/v1/marketplace/asins", json={"asin": "B09ABC4567"}, headers=auth_headers
    )
    assert resp.status_code == 201


def test_asin_format_validated(onboarded_client, auth_headers):
    resp = onboarded_client.post(
        "/api/v1/marketplace/asins", json={"asin": "bad-asin!"}, headers=auth_headers
    )
    assert resp.status_code == 422


def test_duplicate_asin_conflict(onboarded_client, auth_headers):
    onboarded_client.post(
        "/api/v1/marketplace/asins", json={"asin": "B08XYZ1234"}, headers=auth_headers
    )
    resp = onboarded_client.post(
        "/api/v1/marketplace/asins", json={"asin": "B08XYZ1234"}, headers=auth_headers
    )
    assert resp.status_code == 409


def test_asins_tenant_scoped(onboarded_client, auth_headers, fake_db):
    fake_db.seed("tracked_asins", [{"user_id": "other-user", "asin": "B00OTHER99"}])
    listed = onboarded_client.get("/api/v1/marketplace/asins", headers=auth_headers).json()
    assert listed["items"] == []
    assert TEST_USER != "other-user"
