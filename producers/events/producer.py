"""Ticketmaster Discovery events producer (free tier — data_sources.md §5).

Supplementary signal: weak coverage outside major markets is expected.
Events older than 7 days stale are simply dropped (they decay in relevance).
"""
import os
from datetime import timedelta
from typing import Any, Callable

from shared.http import FetchResult, fetch_json
from shared.producer import BaseProducer, Record
from shared.ratelimit import TokenBucket
from weather.producer import Location

API_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
# Free tier: ~5 calls/sec, 5000/day — we use a tiny fraction (1 call/user/day).
BUCKET = TokenBucket(capacity=5, refill_per_sec=1.0)

LARGE_VENUE_HINTS = ("stadium", "arena", "festival", "speedway", "raceway")


def parse_events(user_id: str, body: dict[str, Any]) -> list[Record]:
    events = body.get("_embedded", {}).get("events", [])
    records: list[Record] = []
    for ev in events:
        day = ev.get("dates", {}).get("start", {}).get("localDate")
        if not day:
            continue
        classifications = ev.get("classifications", [{}])
        category = classifications[0].get("segment", {}).get("name", "Other") if classifications else "Other"
        venue_names = " ".join(
            v.get("name", "") for v in ev.get("_embedded", {}).get("venues", [])
        ).lower()
        payload = {
            "user_id": user_id,
            "event_id": ev.get("id"),
            "name": ev.get("name"),
            "category": category,
            "large_venue": any(h in venue_names for h in LARGE_VENUE_HINTS),
        }
        records.append((f"{user_id}:{ev.get('id', day)}", day, payload))
    return records


class EventsProducer(BaseProducer):
    source = "events"
    topic = "signals.events"
    freshness = timedelta(hours=26)   # refreshed daily
    cache_ttl = timedelta(days=7)     # data_sources.md: stale events dropped after 7d

    def __init__(self, publisher, cache, locations: list[Location],
                 radius_km: int = 50,
                 api_key: str | None = None,
                 fetcher: Callable[..., FetchResult] = fetch_json) -> None:
        super().__init__(publisher, cache)
        self.locations = locations
        self.radius_km = radius_km
        self.api_key = api_key or os.environ.get("TICKETMASTER_API_KEY", "")
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        if not self.api_key:
            raise RuntimeError("TICKETMASTER_API_KEY not configured")
        records: list[Record] = []
        for loc in self.locations:
            result = self._fetch(
                API_URL,
                params={
                    "apikey": self.api_key,
                    "latlong": f"{loc.latitude},{loc.longitude}",
                    "radius": self.radius_km,
                    "unit": "km",
                    "size": 100,
                    "sort": "date,asc",
                },
                bucket=BUCKET,
            )
            if not result.ok:
                # 404 = no events near location — valid empty result, not a failure.
                if result.status_code == 404:
                    continue
                raise RuntimeError(f"ticketmaster fetch failed: {result.error}")
            records.extend(parse_events(loc.user_id, result.json))
        return records
