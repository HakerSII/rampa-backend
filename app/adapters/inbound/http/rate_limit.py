"""Fixed-window rate limiter per API key (in-memory, per process)."""
import math
import time
from collections.abc import Callable

from app.domain.errors import RateLimited


class FixedWindowRateLimiter:
    def __init__(self, limit: int, window_s: float = 60.0, now: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.now = now
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (window start, count)

    def hit(self, key: str) -> None:
        now = self.now()
        start, count = self._windows.get(key, (now, 0))
        if now - start >= self.window_s:
            start, count = now, 0
        if count >= self.limit:
            retry = max(1, math.ceil(self.window_s - (now - start)))
            raise RateLimited(f"rate limit {self.limit}/min exceeded", retry_after=retry)
        self._windows[key] = (start, count + 1)
