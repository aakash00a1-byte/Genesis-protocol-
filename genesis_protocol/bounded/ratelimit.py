"""Sliding-window rate limiting for autonomous work (V7 P8).

A ``RateLimiter`` caps how many actions a key may perform inside a window, so a
loop or a hot path cannot exceed a human-set rate even when its budget is large.
It is deliberately small and thread-safe, and it *fails closed*: the first call
for an unknown key is allowed only up to the configured rate.

The limiter answers two questions: ``allow`` (may this happen now?) and
``retry_after`` (how long until it may). Nothing here performs the action.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional


@dataclass
class RateDecision:
    allowed: bool
    retry_after_seconds: float = 0.0
    remaining: int = 0
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {"allowed": self.allowed, "retry_after_seconds": round(self.retry_after_seconds, 3),
                "remaining": self.remaining, "reason": self.reason}


class RateLimiter:
    """A per-key sliding-window limiter."""

    def __init__(self, rate: int = 30, window_seconds: float = 60.0,
                 clock: Optional[Callable[[], float]] = None):
        self.rate = max(0, int(rate))
        self.window_seconds = float(window_seconds)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._hits: Dict[str, Deque[float]] = {}

    def _prune(self, hits: Deque[float], now: float) -> None:
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()

    def check(self, key: str) -> RateDecision:
        now = self._clock()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            self._prune(hits, now)
            if len(hits) >= self.rate:
                wait = 0.0 if not hits else self.window_seconds - (now - hits[0])
                return RateDecision(False, max(0.0, wait), 0, f"rate limit reached for '{key}'")
            return RateDecision(True, 0.0, self.rate - len(hits), "ok")

    def allow(self, key: str, consume: bool = True) -> RateDecision:
        """Check and, by default, record a hit when allowed."""
        decision = self.check(key)
        if decision.allowed and consume:
            with self._lock:
                self._hits.setdefault(key, deque()).append(self._clock())
            decision.remaining = max(0, decision.remaining - 1)
        return decision

    def reset(self, key: Optional[str] = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)

    def status(self) -> Dict[str, object]:
        now = self._clock()
        with self._lock:
            out = {}
            for key, hits in self._hits.items():
                self._prune(hits, now)
                out[key] = {"in_window": len(hits), "rate": self.rate}
            return {"window_seconds": self.window_seconds, "keys": out}
