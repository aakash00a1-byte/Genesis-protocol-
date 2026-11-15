"""Bounded autonomous work (V7 P8).

Autonomy is bounded in units a human can reason about, and every autonomous
action passes through one gate.

* ``budget``    - per-scope hard limits on cost, tokens, requests, tool calls and
                  wall-clock time (fail closed: unknown scope gets a conservative
                  default).
* ``ratelimit`` - per-key sliding-window rate limiting.
* ``runaway``  - detection of repetition, cycling and no-progress loops.
* ``failover`` - bounded provider/model failover with health cooldowns.
* ``governor`` - resource-driven degraded modes (normal/reduced/minimal/halted)
                  with strictest-breach-wins and fail-toward-caution reads.
* ``autonomy`` - ``BoundedAutonomy``: the single gate wrapping kill switch,
                  governor, rate limit, runaway guard and budget, plus provider
                  recovery. It decides; it does not perform work.
"""
from genesis_protocol.bounded.autonomy import AutonomyDecision, BoundedAutonomy, get_bounded_autonomy
from genesis_protocol.bounded.budget import (
    DEFAULT_LIMITS,
    Budget,
    BudgetCheck,
    BudgetExceeded,
    BudgetLedger,
    BudgetLimits,
)
from genesis_protocol.bounded.emergency import LocalKillSwitch, resolve_kill_switch
from genesis_protocol.bounded.failover import Candidate, FailoverChain
from genesis_protocol.bounded.governor import (
    MODES,
    GovernorState,
    ResourceGovernor,
    ResourceReading,
    Thresholds,
)
from genesis_protocol.bounded.ratelimit import RateDecision, RateLimiter
from genesis_protocol.bounded.runaway import RunawayFinding, RunawayGuard

__all__ = [
    "Budget",
    "BudgetCheck",
    "BudgetExceeded",
    "BudgetLedger",
    "BudgetLimits",
    "DEFAULT_LIMITS",
    "RateLimiter",
    "RateDecision",
    "RunawayGuard",
    "RunawayFinding",
    "FailoverChain",
    "Candidate",
    "ResourceGovernor",
    "ResourceReading",
    "GovernorState",
    "Thresholds",
    "MODES",
    "LocalKillSwitch",
    "resolve_kill_switch",
    "BoundedAutonomy",
    "AutonomyDecision",
    "get_bounded_autonomy",
]
