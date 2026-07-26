"""Kafka producer for sales events.

Degrades gracefully: if Kafka is unreachable, events are dropped with a log
line — sales rows are already durable in Supabase, so the stream is a
convenience for the analytics layer, not a point of failure (NFR-3).
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi import Depends

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

SALES_TOPIC = "sales.raw"


class EventProducer(Protocol):
    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        ...


class NullProducer:
    """No-op producer used in tests and when Kafka is disabled/unavailable."""

    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        logger.debug("NullProducer: dropping event topic=%s key=%s", topic, key)


class KafkaEventProducer:
    def __init__(self, bootstrap_servers: str) -> None:
        from kafka import KafkaProducer  # imported lazily so tests need no broker

        self._producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8"),
            retries=3,
        )

    def publish(self, topic: str, key: str, payload: dict[str, Any]) -> None:
        self._producer.send(topic, key=key, value=payload)


def build_sales_envelope(user_id: str, upload_id: str, row: dict[str, Any]) -> dict[str, Any]:
    """Common message envelope (architecture.md §2.4)."""
    return {
        "source": "sales_csv",
        "entity_key": f"{user_id}:{row['sku']}",
        "observed_at": str(row["date"]),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "payload": {"user_id": user_id, "upload_id": upload_id, **row},
    }


_producer: EventProducer | None = None


def get_producer(settings: Settings = Depends(get_settings)) -> EventProducer:
    global _producer
    if _producer is not None:
        return _producer
    if not settings.kafka_enabled:
        _producer = NullProducer()
        return _producer
    try:
        _producer = KafkaEventProducer(settings.kafka_bootstrap_servers)
    except Exception:  # noqa: BLE001 - any broker/client failure must not kill the API
        logger.warning("Kafka unavailable; falling back to NullProducer", exc_info=True)
        _producer = NullProducer()
    return _producer
