"""Open-Meteo weather producer (free, keyless — data_sources.md §1).

Fetches daily forecast + recent observations per configured user location.
"""
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from shared.http import FetchResult, fetch_json
from shared.producer import BaseProducer, Record
from shared.ratelimit import TokenBucket

API_URL = "https://api.open-meteo.com/v1/forecast"
DAILY_VARS = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,snowfall_sum,weather_code"

# ~600/min non-commercial limit; we pace far below it.
BUCKET = TokenBucket(capacity=10, refill_per_sec=0.5)


@dataclass(frozen=True)
class Location:
    user_id: str
    latitude: float
    longitude: float
    timezone: str = "UTC"


def parse_daily(user_id: str, body: dict[str, Any]) -> list[Record]:
    """Open-Meteo daily response -> records (entity: user, observed: date)."""
    daily = body.get("daily", {})
    dates = daily.get("time", [])
    records: list[Record] = []
    for i, day in enumerate(dates):
        payload = {
            "user_id": user_id,
            "temp_max": _at(daily.get("temperature_2m_max"), i),
            "temp_min": _at(daily.get("temperature_2m_min"), i),
            "temp_avg": _at(daily.get("temperature_2m_mean"), i),
            "precip_mm": _at(daily.get("precipitation_sum"), i),
            "snowfall_mm": _at(daily.get("snowfall_sum"), i),
            "weather_code": _at(daily.get("weather_code"), i),
        }
        records.append((user_id, day, payload))
    return records


def _at(series: list | None, i: int) -> Any:
    if not series or i >= len(series):
        return None
    return series[i]


class WeatherProducer(BaseProducer):
    source = "weather"
    topic = "signals.weather"
    freshness = timedelta(hours=26)   # refreshed daily
    cache_ttl = timedelta(hours=24)   # data_sources.md: cache last-known 24h

    def __init__(self, publisher, cache, locations: list[Location],
                 fetcher: Callable[..., FetchResult] = fetch_json) -> None:
        super().__init__(publisher, cache)
        self.locations = locations
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        records: list[Record] = []
        for loc in self.locations:
            result = self._fetch(
                API_URL,
                params={
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                    "daily": DAILY_VARS,
                    "timezone": loc.timezone,
                    "forecast_days": 16,
                    "past_days": 7,
                },
                bucket=BUCKET,
            )
            if not result.ok:
                raise RuntimeError(f"open-meteo fetch failed: {result.error}")
            records.extend(parse_daily(loc.user_id, result.json))
        return records
