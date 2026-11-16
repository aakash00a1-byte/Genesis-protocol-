"""Per-scope budgets for autonomous work (V7 P8).

Autonomy must be bounded in units a human can reason about: money, tokens,
requests, wall-clock time and tool calls. A ``Budget`` is a small, thread-safe
counter for one scope (an agent, a task, a conversation) with hard limits. When a
limit is reached the budget denies the next action; it never silently allows an
overrun.

The budget is *fail closed*: an unknown scope receives a conservative default
budget rather than an unlimited one, and a zero/negative limit means "no allowance
at all".
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Optional


@dataclass
class BudgetLimits:
    """Hard ceilings for one scope. ``0`` means no allowance."""

    cost_usd: float = 1.0
    tokens: int = 100_000
    requests: int = 200
    tool_calls: int = 50
    wall_seconds: float = 900.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


# Conservative default for a scope nobody configured.
DEFAULT_LIMITS = BudgetLimits()


@dataclass
class BudgetCheck:
    """The result of asking whether an action fits inside a budget."""

    allowed: bool
    reason: str
    exceeded: list = field(default_factory=list)
    remaining: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class BudgetExceeded(RuntimeError):
    """Raised when a caller consumes past a hard limit."""


class Budget:
    """A thread-safe counter with hard limits for one scope."""

    def __init__(self, limits: Optional[BudgetLimits] = None,
                 clock: Optional[Callable[[], float]] = None):
        self.limits = limits or DEFAULT_LIMITS
        self._clock = clock or time.monotonic
        self._started = self._clock()
        # Reentrant: consume() calls check() while holding the lock.
        self._lock = threading.RLock()
        self.cost_usd = 0.0
        self.tokens = 0
        self.requests = 0
        self.tool_calls = 0

    # -- state ----------------------------------------------------------------

    def elapsed(self) -> float:
        return max(0.0, self._clock() - self._started)

    def remaining(self) -> Dict[str, float]:
        return {
            "cost_usd": max(0.0, self.limits.cost_usd - self.cost_usd),
            "tokens": max(0, self.limits.tokens - self.tokens),
            "requests": max(0, self.limits.requests - self.requests),
            "tool_calls": max(0, self.limits.tool_calls - self.tool_calls),
            "wall_seconds": max(0.0, self.limits.wall_seconds - self.elapsed()),
        }

    def usage(self) -> Dict[str, float]:
        return {"cost_usd": self.cost_usd, "tokens": self.tokens, "requests": self.requests,
                "tool_calls": self.tool_calls, "wall_seconds": round(self.elapsed(), 3)}

    # -- enforcement ----------------------------------------------------------

    def check(self, cost_usd: float = 0.0, tokens: int = 0, requests: int = 1,
              tool_calls: int = 0) -> BudgetCheck:
        """Whether one more action fits. Does not consume."""
        with self._lock:
            exceeded = []
            if self.cost_usd + cost_usd > self.limits.cost_usd:
                exceeded.append("cost_usd")
            if self.tokens + tokens > self.limits.tokens:
                exceeded.append("tokens")
            if self.requests + requests > self.limits.requests:
                exceeded.append("requests")
            if self.tool_calls + tool_calls > self.limits.tool_calls:
                exceeded.append("tool_calls")
            if self.elapsed() >= self.limits.wall_seconds:
                exceeded.append("wall_seconds")
            if exceeded:
                return BudgetCheck(False, f"budget exceeded: {', '.join(exceeded)}", exceeded, self.remaining())
            return BudgetCheck(True, "within budget", [], self.remaining())

    def consume(self, cost_usd: float = 0.0, tokens: int = 0, requests: int = 1,
                tool_calls: int = 0) -> BudgetCheck:
        """Consume an allowance. Raises if it would exceed a hard limit."""
        with self._lock:
            check = self.check(cost_usd, tokens, requests, tool_calls)
            if not check.allowed:
                raise BudgetExceeded(check.reason)
            self.cost_usd += max(0.0, float(cost_usd))
            self.tokens += max(0, int(tokens))
            self.requests += max(0, int(requests))
            self.tool_calls += max(0, int(tool_calls))
            return BudgetCheck(True, "consumed", [], self.remaining())

    def status(self) -> Dict[str, object]:
        return {"limits": self.limits.to_dict(), "usage": self.usage(), "remaining": self.remaining()}


class BudgetLedger:
    """Owns one ``Budget`` per scope key, with a conservative default."""

    def __init__(self, default_limits: Optional[BudgetLimits] = None,
                 clock: Optional[Callable[[], float]] = None):
        self.default_limits = default_limits or DEFAULT_LIMITS
        self._clock = clock
        self._lock = threading.Lock()
        self._budgets: Dict[str, Budget] = {}
        self._limits: Dict[str, BudgetLimits] = {}

    def configure(self, scope: str, limits: BudgetLimits) -> None:
        with self._lock:
            self._limits[scope] = limits
            self._budgets[scope] = Budget(limits, self._clock)

    def for_scope(self, scope: str) -> Budget:
        with self._lock:
            budget = self._budgets.get(scope)
            if budget is None:
                budget = Budget(self._limits.get(scope, self.default_limits), self._clock)
                self._budgets[scope] = budget
            return budget

    def reset(self, scope: str) -> None:
        with self._lock:
            self._budgets.pop(scope, None)

    def status(self) -> Dict[str, object]:
        with self._lock:
            return {scope: b.status() for scope, b in self._budgets.items()}
