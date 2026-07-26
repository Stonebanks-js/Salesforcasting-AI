"""Common Kafka message envelope (architecture.md §2.4)."""
from datetime import datetime, timezone
from typing import Any


def build_envelope(
    *,
    source: str,
    entity_key: str,
    observed_at: str,
    payload: dict[str, Any],
    schema_version: int = 1,
) -> dict[str, Any]:
    return {
        "source": source,
        "entity_key": entity_key,
        "observed_at": observed_at,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": schema_version,
        "payload": payload,
    }
