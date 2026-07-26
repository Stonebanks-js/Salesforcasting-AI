"""Google Trends producer via pytrends (UNOFFICIAL — data_sources.md §3).

Supplementary signal only: Google may throttle (HTTP 429) at any time.
We batch keywords per category, pace calls slowly, back off hard, and
serve cached values for up to 7 days before degrading.
"""
from datetime import timedelta
from typing import Any, Callable

from shared.producer import BaseProducer, Record

Fetcher = Callable[[list[str], str], dict[str, list[tuple[str, int]]]]
"""fetcher(keywords, geo) -> {keyword: [(date_iso, interest_0_100), ...]}"""


def _pytrends_fetch(keywords: list[str], geo: str) -> dict[str, list[tuple[str, int]]]:
    """Production fetcher wrapping pytrends (import lazily — optional dep)."""
    from pytrends.request import TrendReq  # noqa: PLC0415

    client = TrendReq(hl="en-US", tz=360, retries=2, backoff_factor=2.0)
    client.build_payload(keywords, timeframe="today 3-m", geo=geo)
    df = client.interest_over_time()
    out: dict[str, list[tuple[str, int]]] = {}
    for kw in keywords:
        if kw in df.columns:
            out[kw] = [
                (idx.date().isoformat(), int(row[kw]))
                for idx, row in df.iterrows()
                if not row.get("isPartial", False)
            ]
    return out


def parse_trends(user_id: str, category: str,
                 data: dict[str, list[tuple[str, int]]]) -> list[Record]:
    records: list[Record] = []
    for keyword, points in data.items():
        for day, interest in points:
            payload = {
                "user_id": user_id,
                "category": category,
                "keyword": keyword,
                "interest": max(0, min(100, interest)),
            }
            records.append((f"{user_id}:{category}:{keyword}", day, payload))
    return records


class TrendsProducer(BaseProducer):
    source = "trends"
    topic = "signals.trends"
    freshness = timedelta(hours=12)   # refreshed every 6h with jitter
    cache_ttl = timedelta(days=7)     # data_sources.md: last-known up to 7 days

    def __init__(self, publisher, cache,
                 category_keywords: dict[str, list[str]],  # {user_id:category: keywords}
                 geo_by_user: dict[str, str],
                 fetcher: Fetcher = _pytrends_fetch) -> None:
        super().__init__(publisher, cache)
        self.category_keywords = category_keywords
        self.geo_by_user = geo_by_user
        self._fetch = fetcher

    def fetch_records(self) -> list[Record]:
        records: list[Record] = []
        for uc, keywords in self.category_keywords.items():
            user_id, category = uc.split(":", 1)
            geo = self.geo_by_user.get(user_id, "")
            data = self._fetch(keywords[:3], geo)  # ≤3 keywords per category (quota doc)
            if not data:
                raise RuntimeError(f"pytrends returned no data for {uc}")
            records.extend(parse_trends(user_id, category, data))
        return records
