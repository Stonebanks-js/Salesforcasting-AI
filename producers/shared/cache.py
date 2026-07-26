"""Last-known-value disk cache.

Fallback contract (data_sources.md): when a source is rate-limited or down,
producers re-publish cached payloads marked stale so forecasts degrade
gracefully instead of losing the feature abruptly.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DiskCache:
    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self._dir / f"{safe}.json"

    def write(self, key: str, payload: Any) -> None:
        record = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        self._path(key).write_text(json.dumps(record))

    def read(self, key: str, max_age: timedelta) -> Any | None:
        """Return cached payload if fresher than `max_age`, else None."""
        path = self._path(key)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text())
            cached_at = datetime.fromisoformat(record["cached_at"])
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - cached_at > max_age:
                return None
            return record["payload"]
        except (ValueError, KeyError, json.JSONDecodeError):
            logger.warning("Corrupt cache entry ignored: %s", path)
            return None
