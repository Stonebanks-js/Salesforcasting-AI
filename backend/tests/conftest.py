"""Shared fixtures: app with faked DB/producer, and a JWT minter."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Environment must be set before importing the app (settings are lru_cached).
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret")
os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon")
os.environ.setdefault("KAFKA_ENABLED", "false")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import get_db  # noqa: E402
from app.kafka import get_producer  # noqa: E402
from app.main import create_app  # noqa: E402
from tests.fakes import FakeDb, FakeProducer  # noqa: E402

TEST_USER = "11111111-1111-1111-1111-111111111111"


def mint_token(user_id: str = TEST_USER) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return jwt.encode(payload, "test-secret", algorithm="HS256")


@pytest.fixture
def fake_db() -> FakeDb:
    return FakeDb()


@pytest.fixture
def fake_producer() -> FakeProducer:
    return FakeProducer()


@pytest.fixture
def client(fake_db, fake_producer):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: fake_db
    app.dependency_overrides[get_producer] = lambda: fake_producer
    app.state.limiter.enabled = False  # rate limiting tested separately
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers() -> dict:
    return {"Authorization": f"Bearer {mint_token()}"}


@pytest.fixture
def onboarded_client(client, auth_headers, fake_db):
    """Client whose user has a completed profile + default signal settings."""
    fake_db.seed("profiles", [{
        "id": TEST_USER, "business_name": "Acme", "country_code": "US",
        "city": "Austin", "latitude": 30.27, "longitude": -97.74,
        "timezone": "America/Chicago", "currency": "USD",
        "onboarding_complete": True,
    }])
    fake_db.seed("signal_settings", [
        {"user_id": TEST_USER, "signal": s, "enabled": s != "marketplace"}
        for s in ("weather", "holidays", "trends", "macro", "events", "marketplace")
    ])
    return client
