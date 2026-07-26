def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_protected_endpoint_requires_token(client):
    resp = client.get("/api/v1/profile")
    assert resp.status_code in (401, 403)


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/profile", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
    body = resp.json()
    assert body["status"] == 401  # RFC 7807 problem shape
