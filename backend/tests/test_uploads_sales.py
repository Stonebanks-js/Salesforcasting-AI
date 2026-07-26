"""API tests for the sales upload flow (async 202 + polling pattern)."""
import io

from tests.conftest import TEST_USER

CSV = b"""date,sku,product_name,quantity,revenue
2026-07-01,MUG-001,Ceramic Mug,10,120.50
2026-07-02,MUG-001,Ceramic Mug,5,60.25
2026-07-03,MUG-001,Ceramic Mug,-2,oops
"""


def _upload(client, headers, content=CSV, filename="sales.csv"):
    return client.post(
        "/api/v1/uploads/sales",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
        headers=headers,
    )


def test_upload_flow_end_to_end(onboarded_client, auth_headers, fake_db):
    resp = _upload(onboarded_client, auth_headers)
    assert resp.status_code == 202
    upload_id = resp.json()["upload_id"]
    assert resp.json()["status_url"] == f"/api/v1/uploads/{upload_id}"

    # Background task ran: upload reaches terminal state (TestClient is sync).
    status_resp = onboarded_client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers)
    body = status_resp.json()
    assert body["status"] == "loaded"
    assert body["row_count"] == 2
    rejected = body["error_report"]["rejected_rows"]
    assert len(rejected) == 1 and rejected[0]["row"] == 4

    # Sales rows landed (bad row rejected).
    assert len(fake_db.tables["sales_daily"]) == 2

    # Product created with denormalized stats.
    product = fake_db.tables["products"][0]
    assert product["sku"] == "MUG-001"
    assert product["sales_days"] == 2
    assert product["last_sale_date"] == "2026-07-02"


def test_upload_publishes_kafka_events(onboarded_client, auth_headers, fake_producer):
    _upload(onboarded_client, auth_headers)
    assert len(fake_producer.events) == 2
    topic, key, payload = fake_producer.events[0]
    assert topic == "sales.raw"
    assert key == f"{TEST_USER}:MUG-001"
    assert payload["source"] == "sales_csv"
    assert payload["payload"]["quantity"] == 10.0


def test_reupload_is_idempotent(onboarded_client, auth_headers, fake_db):
    _upload(onboarded_client, auth_headers)
    _upload(onboarded_client, auth_headers)  # same file again
    assert len(fake_db.tables["sales_daily"]) == 2  # upserted, not duplicated


def test_completely_invalid_file_marks_failed(onboarded_client, auth_headers, fake_db):
    resp = _upload(onboarded_client, auth_headers, content=b"not,a,csv\n1,2,3\n")
    upload_id = resp.json()["upload_id"]
    body = onboarded_client.get(f"/api/v1/uploads/{upload_id}", headers=auth_headers).json()
    assert body["status"] == "failed"
    assert "sales_daily" not in fake_db.tables


def test_empty_file_rejected(onboarded_client, auth_headers):
    resp = _upload(onboarded_client, auth_headers, content=b"")
    assert resp.status_code == 400


def test_wrong_extension_rejected(onboarded_client, auth_headers):
    resp = onboarded_client.post(
        "/api/v1/uploads/sales",
        files={"file": ("sales.exe", io.BytesIO(CSV), "application/x-msdownload")},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_uploads_list_scoped_to_user(onboarded_client, auth_headers):
    _upload(onboarded_client, auth_headers)
    resp = onboarded_client.get("/api/v1/uploads", headers=auth_headers)
    assert resp.json()["total"] == 1
