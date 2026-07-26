"""Keepa marketplace producer (free tier, OPT-IN — data_sources.md §6).

Token budget is the binding constraint (~1 token/min refill). We enforce a
strict token bucket, batch ASINs into one call per cycle, and skip the cycle
entirely when tokens are insufficient rather than failing mid-forecast.
"""
import os
from datetime import date, timedelta
from typing import Any, Callable

from shared.http import FetchResult, fetch_json
from shared.producer import BaseProducer, Record
from shared.ratelimit import TokenBucket

API_URL = "https://api.keepa.com/product"
# ~1 token/min refill on the free tier; one product query costs >= 1 token.
BUCKET = TokenBucket(capacity=20, refill_per_sec=1 / 60)


def parse_products(user_id: str, body: dict[str, Any]) -> list[Record]:
    """Keepa /product response -> one record per ASIN for today."""
    today = date.today().isoformat()
    records: list[Record] = []
    for product in body.get("products", []):
        asin = product.get("asin")
        if not asin:
            continue
        csv_series = product.get("csv", [])
        # csv[0] = Amazon price history [keepaTime, price, ...], csv[3] = BSR.
        price = _last_value(csv_series[0] if len(csv_series) > 0 else None)
        bsr = _last_value(csv_series[3] if len(csv_series) > 3 else None)
        payload = {
            "user_id": user_id,
            "asin": asin,
            "price": (price / 100) if isinstance(price, int) and price > 0 else None,
            "bsr": bsr if isinstance(bsr, int) and bsr > 0 else None,
            "title": product.get("title"),
        }
        records.append((f"{user_id}:{asin}", today, payload))
    return records


def _last_value(series: list | None) -> int | None:
    if not series or len(series) < 2:
        return None
    return series[-1]


class MarketplaceProducer(BaseProducer):
    source = "marketplace"
    topic = "signals.marketplace"
    freshness = timedelta(hours=26)   # refreshed daily (strict token budget)
    cache_ttl = timedelta(days=7)     # data_sources.md: last-known 7-day TTL

    def __init__(self, publisher, cache,
                 asins_by_user: dict[str, list[str]],  # hard cap 10 enforced upstream
                 api_key: str | None = None,
                 fetcher: Callable[..., FetchResult] = fetch_json) -> None:
        super().__init__(publisher, cache)
        self.asins_by_user = asins_by_user
        self.api_key = api_key or os.environ.get("KEEPA_API_KEY", "")
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        if not self.api_key:
            raise RuntimeError("KEEPA_API_KEY not configured")
        records: list[Record] = []
        for user_id, asins in self.asins_by_user.items():
            batch = asins[:10]  # belt-and-braces on top of the DB/API cap
            # Token check BEFORE spending: skip cycle if the bucket can't pay.
            if not BUCKET.acquire(tokens=len(batch), timeout=5.0):
                raise RuntimeError("keepa token budget exhausted; cycle skipped")
            result = self._fetch(
                API_URL,
                params={"key": self.api_key, "domain": 1, "asin": ",".join(batch)},
            )
            if not result.ok:
                raise RuntimeError(f"keepa fetch failed: {result.error}")
            records.extend(parse_products(user_id, result.json))
        return records
