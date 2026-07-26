"""FRED macroeconomic series producer (free API key — data_sources.md §4).

Default series: CPIAUCSL (CPI), UMCSENT (consumer sentiment), UNRATE
(unemployment), PCE (consumer spending). Monthly observations forward-fill
cleanly, so staleness tolerance is high.
"""
import os
from datetime import timedelta
from typing import Any, Callable

from shared.http import FetchResult, fetch_json
from shared.producer import BaseProducer, Record
from shared.ratelimit import TokenBucket

API_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_SERIES = ("CPIAUCSL", "UMCSENT", "UNRATE", "PCE")
BUCKET = TokenBucket(capacity=5, refill_per_sec=0.1)


def parse_observations(series_id: str, body: dict[str, Any]) -> list[Record]:
    records: list[Record] = []
    for obs in body.get("observations", []):
        value = obs.get("value", ".")
        if value == ".":  # FRED's missing-data marker
            continue
        day = obs.get("date")
        try:
            payload = {"series": series_id, "value": float(value)}
        except (TypeError, ValueError):
            continue
        records.append((f"{series_id}:{day}", day, payload))
    return records


class MacroProducer(BaseProducer):
    source = "macro"
    topic = "signals.macro"
    freshness = timedelta(days=2)     # checked daily; series update monthly
    cache_ttl = timedelta(days=90)    # data_sources.md: last-known up to 90 days

    def __init__(self, publisher, cache,
                 series: tuple[str, ...] = DEFAULT_SERIES,
                 api_key: str | None = None,
                 fetcher: Callable[..., FetchResult] = fetch_json) -> None:
        super().__init__(publisher, cache)
        self.series = series
        self.api_key = api_key or os.environ.get("FRED_API_KEY", "")
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        if not self.api_key:
            raise RuntimeError("FRED_API_KEY not configured")
        records: list[Record] = []
        for series_id in self.series:
            result = self._fetch(
                API_URL,
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 24,
                },
                bucket=BUCKET,
            )
            if not result.ok:
                raise RuntimeError(f"FRED fetch failed for {series_id}: {result.error}")
            records.extend(parse_observations(series_id, result.json))
        return records
