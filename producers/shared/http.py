"""HTTP GET with retry/backoff honoring free-tier rate limits."""
import logging
import time
from dataclasses import dataclass

import httpx

from shared.backoff import backoff_delay, is_retryable_status
from shared.ratelimit import TokenBucket

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    ok: bool
    status_code: int | None
    json: dict | list | None
    error: str | None = None


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    bucket: TokenBucket | None = None,
    max_attempts: int = 5,
    timeout: float = 30.0,
) -> FetchResult:
    """GET JSON with token-bucket pacing and exponential backoff on 429/5xx."""
    for attempt in range(1, max_attempts + 1):
        if bucket is not None and not bucket.acquire(timeout=120.0):
            return FetchResult(False, None, None, "rate_limiter_timeout")
        try:
            resp = httpx.get(url, params=params, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            logger.warning("HTTP error attempt %d for %s: %s", attempt, url, exc)
            if attempt == max_attempts:
                return FetchResult(False, None, None, str(exc))
            time.sleep(backoff_delay(attempt))
            continue

        if resp.status_code == 200:
            try:
                return FetchResult(True, 200, resp.json())
            except ValueError:
                return FetchResult(False, 200, None, "invalid_json")

        if is_retryable_status(resp.status_code) and attempt < max_attempts:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff_delay(attempt)
            logger.info("Status %d from %s; backing off %.1fs", resp.status_code, url, delay)
            time.sleep(delay)
            continue
        return FetchResult(False, resp.status_code, None, f"http_{resp.status_code}")

    return FetchResult(False, None, None, "max_attempts_exceeded")
