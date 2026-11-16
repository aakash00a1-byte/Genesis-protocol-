"""Action budgets and rate limits for automatic defence (V7 P6).

Automatic defence must be bounded twice over:

* **Per target** - an actor or source can be acted on at most ``per_target``
  times inside ``cooldown_seconds``. This stops a flapping signal from producing
  an endless stream of actions against the same target.
* **Globally** - at most ``global_cap`` automatic actions may be taken inside
  ``global_window_seconds``, and at most ``max_consecutive`` in a row without a
  detection that resolves. This bounds the blast radius if detection misfires.

The budget is consulted *before* an action and consumed *after* it is performed,
so a denied action costs nothing. All decisions are recorded so the reason a
burst stopped is auditable.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Optional


@dataclass
class BudgetDecision:
    allowed: bool
    reason: str
    retry_after_seconds: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason,
                "retry_after_seconds": round(self.retry_after_seconds, 3)}


class ActionBudget:
    """Sliding-window rate limits for automatic defensive actions."""

    def __init__(
        self,
        per_target: int = 1,
        cooldown_seconds: float = 900.0,
        global_cap: int = 20,
        global_window_seconds: float = 3600.0,
        max_consecutive: int = 5,
    ):
        self.per_target = per_target
        self.cooldown_seconds = cooldown_seconds
        self.global_cap = global_cap
        self.global_window_seconds = global_window_seconds
        self.max_consecutive = max_consecutive
        self._lock = threading.Lock()
        self._per_target: Dict[str, float] = {}
        self._global: Deque[float] = deque()
        self._consecutive = 0

    @staticmethod
    def _prune(window: Deque[float], now: float, span: float) -> None:
        while window and now - window[0] > span:
            window.popleft()

    def check(self, key: str, now: Optional[float] = None) -> BudgetDecision:
        """Whether an automatic action on ``key`` is within budget right now."""
        now = time.monotonic() if now is None else now
        with self._lock:
            last = self._per_target.get(key)
            if last is not None:
                elapsed = now - last
                if elapsed < self.cooldown_seconds:
                    wait = self.cooldown_seconds - elapsed
                    return BudgetDecision(False, f"cooldown active for '{key}'", wait)
            self._prune(self._global, now, self.global_window_seconds)
            if len(self._global) >= self.global_cap:
                wait = self.global_window_seconds - (now - self._global[0])
                return BudgetDecision(False, "global automatic-action cap reached", max(0.0, wait))
            if self._consecutive >= self.max_consecutive:
                return BudgetDecision(False, "too many consecutive automatic actions", 0.0)
            return BudgetDecision(True, "within budget")

    def consume(self, key: str, now: Optional[float] = None) -> None:
        """Record that an automatic action on ``key`` was performed."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._per_target[key] = now
            self._prune(self._global, now, self.global_window_seconds)
            self._global.append(now)
            self._consecutive += 1

    def note_quiet_pass(self) -> None:
        """Reset the consecutive counter after a pass with no automatic action."""
        with self._lock:
            self._consecutive = 0

    def reset(self) -> None:
        with self._lock:
            self._per_target.clear()
            self._global.clear()
            self._consecutive = 0

    def status(self, now: Optional[float] = None) -> Dict[str, object]:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._prune(self._global, now, self.global_window_seconds)
            return {
                "per_target": self.per_target,
                "cooldown_seconds": self.cooldown_seconds,
                "global_cap": self.global_cap,
                "global_used": len(self._global),
                "consecutive": self._consecutive,
                "max_consecutive": self.max_consecutive,
            }
