"""Supabase-backed Publisher (serverless mode, decision 027).

Drop-in for the Kafka Publisher protocol: signal envelopes are inserted into
the ``signal_events`` table; health reports are upserted into
``signal_status``. Lets every producer run unchanged in CI without a broker.
"""
import logging
from typing import Any, Protocol

from shared.producer import Publisher  # noqa: F401  (protocol re-export)

logger = logging.getLogger(__name__)

HEALTH_TOPIC = "signals.health"


class DbLike(Protocol):
    def table(self, name: str): ...


class SupabasePublisher:
    """Publisher that persists envelopes/health to Supabase instead of Kafka."""

    def __init__(self, client: DbLike) -> None:
        self._db = client

    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        if topic == HEALTH_TOPIC:
            self._db.table("signal_status").upsert({
                "signal": payload.get("source") or key,
                "status": payload.get("status", "degraded"),
                "last_success_at": payload.get("last_success_at"),
                "last_error": payload.get("error"),
            }).execute()
            return
        self._db.table("signal_events").insert({
            "source": payload.get("source", topic),
            "entity_key": payload.get("entity_key", key),
            "observed_at": payload.get("observed_at"),
            "payload": payload.get("payload", payload),
        }).execute()
