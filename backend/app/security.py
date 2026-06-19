import time
from collections import defaultdict, deque
from threading import Lock


class RateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            entries = self._requests[key]
            while entries and entries[0] < cutoff:
                entries.popleft()
            if len(entries) >= limit:
                return False
            entries.append(now)
            if len(self._requests) > 10_000:
                self._requests = defaultdict(deque, {name: values for name, values in self._requests.items() if values and values[-1] >= cutoff})
            return True


rate_limiter = RateLimiter()
