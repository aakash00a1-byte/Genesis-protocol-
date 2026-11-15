"""Bounded autonomous work (V7 P8).

Ties the P8 primitives into one gate that every autonomous action passes through.
An action is allowed only if **all** of these hold, checked in order, each able to
refuse on its own:

1. the emergency kill switch (shared with P6) is not engaged;
2. the resource governor's mode permits the kind of work;
3. the scope's rate limit has room;
4. the scope's budget has room;
5. the runaway guard has not flagged the current step stream.

On success the action's cost/tokens are consumed and the step is recorded. On any
refusal the reason is returned and nothing is consumed - a refused action is free.

The controller performs no work itself; it only decides. This keeps autonomy
bounded and auditable, and lets the same gate wrap chat, tool calls, background
tasks and provider calls. Provider failure recovery is delegated to
:class:`FailoverChain`; degradation to :class:`ResourceGovernor`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from genesis_protocol.bounded.budget import BudgetExceeded, BudgetLedger
from genesis_protocol.bounded.failover import FailoverChain
from genesis_protocol.bounded.governor import ResourceGovernor
from genesis_protocol.bounded.ratelimit import RateLimiter
from genesis_protocol.bounded.runaway import RunawayGuard


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AutonomyDecision:
    allowed: bool
    reason: str
    scope: str
    action: str
    mode: str = "normal"
    runaway: Optional[Dict[str, Any]] = None
    remaining: Dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BoundedAutonomy:
    """The single gate for bounded autonomous work."""

    def __init__(
        self,
        budgets: Optional[BudgetLedger] = None,
        limiter: Optional[RateLimiter] = None,
        governor: Optional[ResourceGovernor] = None,
        failover: Optional[FailoverChain] = None,
        kill_switch: Optional[Any] = None,
        cost_tracker: Optional[Any] = None,
    ):
        self.budgets = budgets or BudgetLedger()
        self.limiter = limiter or RateLimiter()
        self.governor = governor or ResourceGovernor()
        self.failover = failover or FailoverChain()
        self._kill_switch = kill_switch
        self._cost_tracker = cost_tracker
        self._guards: Dict[str, RunawayGuard] = {}

    @property
    def kill_switch(self) -> Any:
        if self._kill_switch is None:
            from genesis_protocol.guardian.killswitch import get_kill_switch

            self._kill_switch = get_kill_switch()
        return self._kill_switch

    @property
    def cost_tracker(self) -> Any:
        if self._cost_tracker is None:
            from genesis_protocol.survival.cost_tracker import get_cost_tracker

            self._cost_tracker = get_cost_tracker()
        return self._cost_tracker

    def guard_for(self, scope: str) -> RunawayGuard:
        guard = self._guards.get(scope)
        if guard is None:
            guard = RunawayGuard()
            self._guards[scope] = guard
        return guard

    # -- the gate -------------------------------------------------------------

    def authorize(
        self,
        scope: str,
        action: str,
        work: str = "standard",
        signature: str = "",
        progress: str = "",
        cost_usd: float = 0.0,
        tokens: int = 0,
        tool_calls: int = 0,
    ) -> AutonomyDecision:
        """Decide whether one autonomous action may proceed (and consume if so)."""
        # 1. kill switch
        if self.kill_switch.is_engaged():
            return AutonomyDecision(False, "kill switch engaged", scope, action)

        # 2. resource governor
        state = self.governor.evaluate()
        if not self.governor.permits(state.mode, work):
            return AutonomyDecision(False, f"resource mode '{state.mode}' blocks '{work}' work",
                                    scope, action, mode=state.mode)

        # 3. rate limit (checked, not consumed - a refused action costs nothing)
        rate = self.limiter.check(scope)
        if not rate.allowed:
            return AutonomyDecision(False, rate.reason, scope, action, mode=state.mode)

        # 4. runaway guard (records the attempt stream, so a loop of denied
        #    attempts is still detected)
        finding = self.guard_for(scope).record(action, signature, progress)
        if finding is not None:
            return AutonomyDecision(False, f"runaway {finding.kind}: {finding.reason}",
                                    scope, action, mode=state.mode, runaway=finding.to_dict())

        # 5. budget
        budget = self.budgets.for_scope(scope)
        check = budget.check(cost_usd=cost_usd, tokens=tokens, tool_calls=tool_calls)
        if not check.allowed:
            return AutonomyDecision(False, check.reason, scope, action, mode=state.mode,
                                    remaining=check.remaining)
        try:
            budget.consume(cost_usd=cost_usd, tokens=tokens, tool_calls=tool_calls)
        except BudgetExceeded as exc:  # race between check and consume
            return AutonomyDecision(False, str(exc), scope, action, mode=state.mode)

        # All gates passed: record the rate hit and the cost.
        self.limiter.allow(scope, consume=True)
        if cost_usd > 0:
            try:
                self.cost_tracker.track("bounded", tokens, cost_usd, model=action)
            except Exception:
                pass
        return AutonomyDecision(True, "within all bounds", scope, action, mode=state.mode,
                                remaining=budget.remaining())

    # -- provider recovery ----------------------------------------------------

    def next_provider(self) -> Optional[Dict[str, Any]]:
        candidate = self.failover.next_candidate()
        return candidate.to_dict() if candidate else None

    def report_provider(self, name: str, ok: bool, error: str = "") -> Dict[str, Any]:
        return self.failover.report(name, ok, error).to_dict()

    # -- read side ------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "kill_switch": self.kill_switch.status(),
            "mode": self.governor.mode(),
            "budgets": self.budgets.status(),
            "rate": self.limiter.status(),
            "failover": self.failover.status(),
        }


_default: Optional[BoundedAutonomy] = None


def get_bounded_autonomy() -> BoundedAutonomy:
    global _default
    if _default is None:
        _default = BoundedAutonomy()
    return _default
