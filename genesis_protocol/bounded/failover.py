"""Bounded failover across providers/models (V7 P8).

When a provider fails, autonomy should try a *bounded* number of alternatives and
then stop - not retry forever. ``FailoverChain`` holds an ordered list of
candidates, marks one unhealthy for a cooldown after repeated failures, and
returns the next healthy candidate. Every attempt is counted against a per-call
attempt cap.

The chain is a pure selection helper: the caller performs the call and reports the
outcome. Selection is deterministic (order is preserved, unhealthy entries are
skipped until their cooldown expires), so behaviour is reproducible.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class Candidate:
    name: str
    provider: str
    model: str = ""
    healthy: bool = True
    failures: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class FailoverChain:
    """Selects the next healthy candidate and tracks bounded failures."""

    def __init__(self, candidates: Optional[List[Candidate]] = None,
                 max_attempts: int = 3, failure_threshold: int = 2,
                 cooldown_seconds: float = 120.0,
                 clock: Optional[Callable[[], float]] = None):
        self.max_attempts = max(1, int(max_attempts))
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._candidates: List[Candidate] = list(candidates or [])

    def add(self, name: str, provider: str, model: str = "") -> Candidate:
        candidate = Candidate(name=name, provider=provider, model=model)
        with self._lock:
            self._candidates.append(candidate)
        return candidate

    def _healthy(self, candidate: Candidate, now: float) -> bool:
        if candidate.healthy:
            return True
        # Unhealthy only until the cooldown expires; then it is retried.
        return candidate.cooldown_until <= now

    def next_candidate(self) -> Optional[Candidate]:
        """The next healthy candidate, or None if none are available."""
        now = self._clock()
        with self._lock:
            for candidate in self._candidates:
                if self._healthy(candidate, now):
                    return candidate
        return None

    def plan(self, max_attempts: Optional[int] = None) -> List[Candidate]:
        """The ordered list of healthy candidates to try, capped by attempts."""
        limit = self.max_attempts if max_attempts is None else max(1, int(max_attempts))
        now = self._clock()
        with self._lock:
            healthy = [c for c in self._candidates if self._healthy(c, now)]
        return healthy[:limit]

    def report(self, name: str, ok: bool, error: str = "") -> Candidate:
        """Record the outcome of one attempt against a candidate."""
        now = self._clock()
        with self._lock:
            for candidate in self._candidates:
                if candidate.name != name:
                    continue
                if ok:
                    candidate.failures = 0
                    candidate.healthy = True
                    candidate.last_error = ""
                else:
                    candidate.failures += 1
                    candidate.last_error = error
                    if candidate.failures >= self.failure_threshold:
                        candidate.healthy = False
                        candidate.cooldown_until = now + self.cooldown_seconds
                return candidate
        raise KeyError(f"unknown candidate '{name}'")

    def reset(self, name: Optional[str] = None) -> None:
        with self._lock:
            for candidate in self._candidates:
                if name is None or candidate.name == name:
                    candidate.healthy = True
                    candidate.failures = 0
                    candidate.cooldown_until = 0.0
                    candidate.last_error = ""

    def status(self) -> Dict[str, object]:
        now = self._clock()
        with self._lock:
            return {
                "candidates": [c.to_dict() for c in self._candidates],
                "healthy": [c.name for c in self._candidates if self._healthy(c, now)],
                "max_attempts": self.max_attempts,
            }
