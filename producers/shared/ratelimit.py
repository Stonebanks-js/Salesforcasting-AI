"""Token-bucket rate limiter — keeps every source inside its free-tier quota."""
import time


class TokenBucket:
    """Capacity `capacity` tokens, refilling at `refill_per_sec`."""

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        if capacity <= 0 or refill_per_sec <= 0:
            raise ValueError("capacity and refill_per_sec must be > 0")
        self.capacity = float(capacity)
        self.refill_per_sec = float(refill_per_sec)
        self._tokens = float(capacity)
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
        self._last = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Consume `tokens` if available; never blocks."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def acquire(self, tokens: float = 1.0, timeout: float = 60.0) -> bool:
        """Block until tokens are available or `timeout` seconds elapse."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.try_acquire(tokens):
                return True
            needed = (tokens - self._tokens) / self.refill_per_sec
            time.sleep(min(max(needed, 0.01), 1.0))
        return False

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens
