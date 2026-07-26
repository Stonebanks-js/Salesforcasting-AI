from tests.conftest import TEST_USER

PROFILE = {
    "business_name": "Acme Crafts",
    "country_code": "us",
    "city": "Austin",
    "latitude": 30.2672,
    "longitude": -97.7431,
    "timezone": "America/Chicago",
    "currency": "usd",
}


def test_put_profile_creates_and_seeds_signal_defaults(client, auth_headers, fake_db):
    resp = client.put("/api/v1/profile", json=PROFILE, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["onboarding_complete"] is True
    assert body["country_code"] == "US"  # normalized to upper

    settings = fake_db.tables["signal_settings"]
    assert len(settings) == 6
    marketplace = next(s for s in settings if s["signal"] == "marketplace")
    assert marketplace["enabled"] is False  # opt-in per PRD
    assert all(s["enabled"] for s in settings if s["signal"] != "marketplace")


def test_put_profile_does_not_clobber_existing_toggles(client, auth_headers, fake_db):
    fake_db.seed("signal_settings", [
        {"user_id": TEST_USER, "signal": "trends", "enabled": False},
    ])
    client.put("/api/v1/profile", json=PROFILE, headers=auth_headers)
    trends = next(s for s in fake_db.tables["signal_settings"] if s["signal"] == "trends")
    assert trends["enabled"] is False  # user choice preserved


def test_get_profile_404_before_onboarding(client, auth_headers):
    resp = client.get("/api/v1/profile", headers=auth_headers)
    assert resp.status_code == 404


def test_profile_validation_rejects_bad_latitude(client, auth_headers):
    resp = client.put("/api/v1/profile", json={**PROFILE, "latitude": 123}, headers=auth_headers)
    assert resp.status_code == 422
    assert resp.json()["status"] == 422
