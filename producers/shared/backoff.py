"""Exponential backoff with jitter for rate-limited/unreliable free APIs."""
import random


def backoff_delay(
    attempt: int,
    *,
    base: float = 1.0,
    factor: float = 2.0,
    max_delay: float = 3600.0,
    jitter: float = 0.25,
    rng: random.Random | None = None,
) -> float:
    """Delay in seconds before retry `attempt` (1-based).

    delay = min(base * factor**(attempt-1), max_delay) * (1 ± jitter)
    """
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    rng = rng or random
    delay = min(base * (factor ** (attempt - 1)), max_delay)
    spread = delay * jitter
    return delay + rng.uniform(-spread, spread)


def is_retryable_status(status: int) -> bool:
    """429 (rate limited) and 5xx are worth retrying; 4xx (except 429) are not."""
    return status == 429 or 500 <= status < 600
