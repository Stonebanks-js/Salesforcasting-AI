"""Shared lib tests: envelope, rate limiter, backoff, cache, health."""
import random
import time
from datetime import datetime, timedelta, timezone

import pytest

from shared.backoff import backoff_delay, is_retryable_status
from shared.cache import DiskCache
from shared.envelope import build_envelope
from shared.health import compute_status
from shared.ratelimit import TokenBucket


def test_envelope_shape():
    env = build_envelope(source="weather", entity_key="u1",
                         observed_at="2026-07-26", payload={"temp": 30})
    assert env["source"] == "weather"
    assert env["schema_version"] == 1
    assert "ingested_at" in env
    assert env["payload"] == {"temp": 30}


def test_token_bucket_allows_burst_then_throttles():
    bucket = TokenBucket(capacity=3, refill_per_sec=0.001)  # ~no refill
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False  # exhausted


def test_token_bucket_refills():
    bucket = TokenBucket(capacity=1, refill_per_sec=50)
    assert bucket.try_acquire() is True
    time.sleep(0.05)  # 50/sec -> ~2.5 tokens refilled, capped at 1
    assert bucket.try_acquire() is True


def test_token_bucket_rejects_bad_config():
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, refill_per_sec=1)


def test_backoff_grows_and_caps():
    rng = random.Random(1)
    d1 = backoff_delay(1, base=1, factor=2, jitter=0, rng=rng)
    d2 = backoff_delay(2, base=1, factor=2, jitter=0, rng=rng)
    d10 = backoff_delay(10, base=1, factor=2, max_delay=60, jitter=0, rng=rng)
    assert d1 == 1 and d2 == 2 and d10 == 60


def test_backoff_jitter_stays_near_nominal():
    rng = random.Random(7)
    for attempt in range(1, 6):
        nominal = min(2 ** (attempt - 1), 3600)
        delay = backoff_delay(attempt, jitter=0.25, rng=rng)
        assert nominal * 0.75 <= delay <= nominal * 1.25


def test_retryable_statuses():
    assert is_retryable_status(429) and is_retryable_status(503)
    assert not is_retryable_status(400) and not is_retryable_status(404)


def test_disk_cache_roundtrip(tmp_path):
    cache = DiskCache(tmp_path)
    cache.write("weather", [("k", "2026-07-26", {"temp": 30})])
    # JSON round-trip normalizes tuples to lists — payload equality is what matters.
    assert cache.read("weather", timedelta(hours=1)) == [["k", "2026-07-26", {"temp": 30}]]
    assert cache.read("weather", timedelta(seconds=0)) is None  # expired
    assert cache.read("missing", timedelta(hours=1)) is None


def test_disk_cache_ignores_corrupt_entry(tmp_path):
    cache = DiskCache(tmp_path)
    cache._path("bad").write_text("{not json")
    assert cache.read("bad", timedelta(hours=1)) is None


NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def test_health_status_transitions():
    fresh = timedelta(hours=1)
    ttl = timedelta(days=1)
    assert compute_status(last_success_at=NOW - timedelta(minutes=30),
                          freshness=fresh, cache_ttl=ttl, now=NOW) == "live"
    assert compute_status(last_success_at=NOW - timedelta(hours=2),
                          freshness=fresh, cache_ttl=ttl, now=NOW) == "stale"
    assert compute_status(last_success_at=NOW - timedelta(days=2),
                          freshness=fresh, cache_ttl=ttl, now=NOW) == "degraded"
    assert compute_status(last_success_at=None,
                          freshness=fresh, cache_ttl=ttl, now=NOW) == "degraded"
