"""Nager.Date public-holiday producer (free, keyless — data_sources.md §2).

Holidays are deterministic and fetched once per year per country; fully
cacheable, so outage impact is negligible.
"""
from datetime import date, timedelta
from typing import Any, Callable

from shared.http import FetchResult, fetch_json
from shared.producer import BaseProducer, Record
from shared.ratelimit import TokenBucket

API_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
BUCKET = TokenBucket(capacity=5, refill_per_sec=0.1)


def parse_holidays(country_code: str, body: list[dict[str, Any]]) -> list[Record]:
    records: list[Record] = []
    for h in body:
        day = h.get("date")
        if not day:
            continue
        payload = {
            "country_code": country_code,
            "local_name": h.get("localName"),
            "name": h.get("name"),
            "global": bool(h.get("global", True)),
            "counties": h.get("counties") or [],
        }
        records.append((f"{country_code}:{day}", day, payload))
    return records


class HolidaysProducer(BaseProducer):
    source = "holidays"
    topic = "signals.holidays"
    freshness = timedelta(days=30)    # refreshed rarely; data is static per year
    cache_ttl = timedelta(days=365)   # data_sources.md: cacheable for a year

    def __init__(self, publisher, cache, country_codes: list[str],
                 fetcher: Callable[..., FetchResult] = fetch_json) -> None:
        super().__init__(publisher, cache)
        self.country_codes = country_codes
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        year = date.today().year
        records: list[Record] = []
        for cc in self.country_codes:
            for y in {year, year + 1}:  # include next year for lookahead features
                result = self._fetch(API_URL.format(year=y, country=cc), bucket=BUCKET)
                if not result.ok:
                    raise RuntimeError(f"nager fetch failed for {cc}/{y}: {result.error}")
                records.extend(parse_holidays(cc, result.json))
        return records
