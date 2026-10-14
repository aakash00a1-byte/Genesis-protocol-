"""Sliding-window rate limiter with per-identity buckets."""
from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, limit_per_minute: int, key: str = "default") -> None:
        self.limit = max(1, limit_per_minute)
        self.default_key = key
        self._window_sec = 60.0
        # key -> list of recent hit timestamps
        self._buckets: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str | None = None) -> bool:
        """Consume one token for `key` (or the default key). True if allowed."""
        bucket_key = key or self.default_key
        now = time.time()
        with self._lock:
            hits = [
                t
                for t in self._buckets.get(bucket_key, [])
                if now - t < self._window_sec
            ]
            if len(hits) >= self.limit:
                self._buckets[bucket_key] = hits
                return False
            hits.append(now)
            self._buckets[bucket_key] = hits
        return True

    def remaining(self, key: str | None = None) -> int:
        bucket_key = key or self.default_key
        now = time.time()
        with self._lock:
            hits = [
                t
                for t in self._buckets.get(bucket_key, [])
                if now - t < self._window_sec
            ]
            return max(0, self.limit - len(hits))

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)