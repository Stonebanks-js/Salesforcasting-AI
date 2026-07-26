"""Feed health computation and reporting (data_sources.md §Quota Monitoring).

Status semantics:
- live:     last successful fetch within the source's freshness window
- stale:    serving cached last-known values within their TTL
- degraded: no fresh data and cache past TTL — features will be excluded
- disabled: user toggle off (set by the config layer, not the producer loop)
"""
from datetime import datetime, timedelta, timezone
from typing import Literal

HealthStatus = Literal["live", "stale", "degraded", "disabled"]


def compute_status(
    *,
    last_success_at: datetime | None,
    freshness: timedelta,
    cache_ttl: timedelta,
    now: datetime | None = None,
) -> HealthStatus:
    now = now or datetime.now(timezone.utc)
    if last_success_at is None:
        # Never succeeded: only "degraded" is honest (there is no cache to serve).
        return "degraded"
    if last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    age = now - last_success_at
    if age <= freshness:
        return "live"
    if age <= freshness + cache_ttl:
        return "stale"
    return "degraded"
