"""Base producer: success path publishes + caches; failure falls back to
stale cache; no cache degrades. This is NFR-3 at the ingestion level."""
from datetime import timedelta

from shared.cache import DiskCache
from shared.producer import BaseProducer


class FakePublisher:
    def __init__(self):
        self.events = []

    def publish(self, topic, key, payload):
        self.events.append((topic, key, payload))


class DummyProducer(BaseProducer):
    source = "dummy"
    topic = "signals.dummy"
    freshness = timedelta(hours=1)
    cache_ttl = timedelta(days=1)

    def __init__(self, publisher, cache, records=None, fail=False):
        super().__init__(publisher, cache)
        self._records = records or []
        self._fail = fail

    def fetch_records(self):
        if self._fail:
            raise RuntimeError("source down")
        return self._records


RECORDS = [("u1", "2026-07-26", {"value": 1}), ("u2", "2026-07-26", {"value": 2})]


def test_success_publishes_and_caches(tmp_path):
    pub = FakePublisher()
    cache = DiskCache(tmp_path)
    report = DummyProducer(pub, cache, records=RECORDS).run_once()
    assert report.status == "live" and report.published == 2 and not report.from_cache
    assert len(pub.events) == 2
    topic, key, env = pub.events[0]
    assert topic == "signals.dummy"
    assert env["source"] == "dummy"
    # JSON round-trip normalizes tuples to lists.
    assert cache.read("dummy", timedelta(days=1)) == [list(r) for r in RECORDS]


def test_failure_republishes_cache_marked_stale(tmp_path):
    pub = FakePublisher()
    cache = DiskCache(tmp_path)
    # Prime the cache with a successful run.
    DummyProducer(pub, cache, records=RECORDS).run_once()
    pub.events.clear()
    # Now fail: cached data is republished with stale=True.
    report = DummyProducer(pub, cache, fail=True).run_once()
    assert report.from_cache is True
    assert report.published == 2
    assert report.status in ("stale", "live")  # depends on last_success age
    assert all(e[2]["payload"]["stale"] is True for e in pub.events)
    assert report.error == "source down"


def test_failure_without_cache_degrades(tmp_path):
    pub = FakePublisher()
    report = DummyProducer(pub, DiskCache(tmp_path), fail=True).run_once()
    assert report.published == 0
    assert report.status == "degraded"
    assert pub.events == []
