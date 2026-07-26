"""Base producer: fetch → envelope → publish, with cache fallback + health.

Subclasses implement ``fetch_records()`` returning a list of
``(entity_key, observed_at, payload)`` tuples. On fetch failure the base
class re-publishes cached payloads (if within TTL) and reports health.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from shared.cache import DiskCache
from shared.envelope import build_envelope
from shared.health import HealthStatus, compute_status

logger = logging.getLogger(__name__)

Record = tuple[str, str, dict[str, Any]]  # (entity_key, observed_at, payload)


class Publisher(Protocol):
    def publish(self, topic: str, key: str, payload: dict) -> None: ...


@dataclass
class RunReport:
    source: str
    status: HealthStatus
    published: int
    from_cache: bool
    error: str | None = None


class BaseProducer:
    source: str = "base"
    topic: str = "signals.base"
    freshness: timedelta = timedelta(hours=12)
    cache_ttl: timedelta = timedelta(days=7)

    def __init__(self, publisher: Publisher, cache: DiskCache) -> None:
        self.publisher = publisher
        self.cache = cache
        self.last_success_at: datetime | None = None

    def fetch_records(self) -> list[Record]:
        raise NotImplementedError

    def run_once(self, now: datetime | None = None) -> RunReport:
        now = now or datetime.now(timezone.utc)
        try:
            records = self.fetch_records()
        except Exception as exc:  # noqa: BLE001 - any source failure must degrade, not crash
            logger.warning("%s fetch failed: %s", self.source, exc)
            return self._fallback(str(exc), now)

        for key, observed_at, payload in records:
            envelope = build_envelope(
                source=self.source, entity_key=key,
                observed_at=observed_at, payload=payload,
            )
            self.publisher.publish(self.topic, key=key, payload=envelope)

        if records:
            self.cache.write(self.source, records)
        self.last_success_at = now
        return RunReport(self.source, "live", len(records), from_cache=False)

    def _fallback(self, error: str, now: datetime) -> RunReport:
        cached = self.cache.read(self.source, self.cache_ttl)
        published = 0
        if cached:
            for key, observed_at, payload in cached:
                stale_payload = {**payload, "stale": True}
                envelope = build_envelope(
                    source=self.source, entity_key=key,
                    observed_at=observed_at, payload=stale_payload,
                )
                self.publisher.publish(self.topic, key=key, payload=envelope)
                published += 1

        status = compute_status(
            last_success_at=self.last_success_at,
            freshness=self.freshness,
            cache_ttl=self.cache_ttl,
            now=now,
        )
        if cached and status == "degraded":
            status = "stale"  # cache present within TTL keeps us at stale
        return RunReport(self.source, status, published, from_cache=bool(cached), error=error)
