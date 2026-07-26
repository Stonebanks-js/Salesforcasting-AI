"""Upload rate limiting (contract: 10 uploads/hour). Runs on its own app
instance so the in-memory limiter state is isolated."""
import io

import pytest
from fastapi.testclient import TestClient

from app.db import get_db
from app.kafka import get_producer
from app.main import create_app
from tests.conftest import mint_token
from tests.fakes import FakeDb, FakeProducer

CSV = b"date,sku,product_name,quantity,revenue\n2026-07-01,A,W,1,10\n"


@pytest.fixture
def limited_client():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: FakeDb()
    app.dependency_overrides[get_producer] = lambda: FakeProducer()
    app.state.limiter.enabled = True
    with TestClient(app) as c:
        yield c


def test_upload_rate_limit_11th_request_rejected(limited_client):
    headers = {"Authorization": f"Bearer {mint_token()}"}
    last = None
    for _ in range(11):
        last = limited_client.post(
            "/api/v1/uploads/sales",
            files={"file": ("s.csv", io.BytesIO(CSV), "text/csv")},
            headers=headers,
        )
    assert last.status_code == 429
