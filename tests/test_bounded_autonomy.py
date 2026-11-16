"""Contract tests for bounded cost-aware autonomy (V7 P8).

Covers the requirement set: budgets, rate limits, runaway detection, bounded
failover, degraded modes, and the single gate that enforces them - plus the
safety invariants (fail closed, refused-is-free, no unbounded retry).
"""
from __future__ import annotations

import threading

import pytest

from genesis_protocol.bounded import (
    BoundedAutonomy,
    Budget,
    BudgetExceeded,
    BudgetLedger,
    BudgetLimits,
    FailoverChain,
    LocalKillSwitch,
    RateLimiter,
    ResourceGovernor,
    ResourceReading,
    RunawayGuard,
    Thresholds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Clock:
    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _governor(cpu=10.0, mem=20.0, disk=30.0, thresholds=None):
    reading = ResourceReading(cpu, mem, disk)
    return ResourceGovernor(sampler=lambda: reading, thresholds=thresholds)


def _autonomy(**kw):
    # P8 must not require P6 to run: the gate falls back to a local, fail-closed
    # switch when the canonical one is absent. Tests inject the same fallback so
    # they are hermetic and independent of the P6 branch.
    kw.setdefault("kill_switch", LocalKillSwitch())
    kw.setdefault("governor", _governor())
    return BoundedAutonomy(**kw)


# ---------------------------------------------------------------------------
# 1. Budgets
# ---------------------------------------------------------------------------

class TestBudget:
    def test_within_budget_consumes(self):
        b = Budget(BudgetLimits(cost_usd=1.0, tokens=100, requests=10, tool_calls=5, wall_seconds=100))
        b.consume(cost_usd=0.25, tokens=10, tool_calls=1)
        assert b.cost_usd == 0.25 and b.tokens == 10 and b.requests == 1 and b.tool_calls == 1

    def test_over_budget_raises_and_does_not_consume(self):
        b = Budget(BudgetLimits(cost_usd=0.10, tokens=10, requests=1, tool_calls=1, wall_seconds=100))
        with pytest.raises(BudgetExceeded):
            b.consume(cost_usd=0.50)
        assert b.cost_usd == 0.0  # refused is free

    def test_zero_limit_means_no_allowance(self):
        b = Budget(BudgetLimits(cost_usd=0.0, tokens=0, requests=0, tool_calls=0, wall_seconds=0))
        assert b.check().allowed is False

    def test_wall_clock_limit(self):
        clock = Clock()
        b = Budget(BudgetLimits(cost_usd=1, tokens=1, requests=1, tool_calls=1, wall_seconds=10), clock=clock)
        assert b.check().allowed is True
        clock.advance(11)
        assert "wall_seconds" in b.check().exceeded

    def test_ledger_fail_closed_default(self):
        ledger = BudgetLedger(default_limits=BudgetLimits(cost_usd=0.5))
        assert ledger.for_scope("never-seen").limits.cost_usd == 0.5

    def test_ledger_configure_and_reset(self):
        ledger = BudgetLedger()
        ledger.configure("agent", BudgetLimits(cost_usd=2.0))
        assert ledger.for_scope("agent").limits.cost_usd == 2.0
        ledger.for_scope("agent").consume(cost_usd=1.0)
        ledger.reset("agent")
        assert ledger.for_scope("agent").cost_usd == 0.0

    def test_concurrent_consume_is_atomic(self):
        b = Budget(BudgetLimits(cost_usd=100.0, tokens=10_000, requests=1000, tool_calls=1000, wall_seconds=1000))
        errors = []

        def worker():
            try:
                for _ in range(50):
                    b.consume(cost_usd=0.01)
            except BudgetExceeded as exc:  # pragma: no cover - not expected here
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert b.cost_usd == pytest.approx(8 * 50 * 0.01)


# ---------------------------------------------------------------------------
# 2. Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_up_to_rate_then_blocks(self):
        clock = Clock()
        rl = RateLimiter(rate=3, window_seconds=60, clock=clock)
        assert all(rl.allow("k").allowed for _ in range(3))
        denied = rl.allow("k")
        assert denied.allowed is False and denied.retry_after_seconds > 0

    def test_window_slides(self):
        clock = Clock()
        rl = RateLimiter(rate=2, window_seconds=10, clock=clock)
        rl.allow("k")
        rl.allow("k")
        assert rl.allow("k").allowed is False
        clock.advance(11)
        assert rl.allow("k").allowed is True

    def test_keys_are_independent(self):
        rl = RateLimiter(rate=1)
        assert rl.allow("a").allowed is True
        assert rl.allow("b").allowed is True
        assert rl.allow("a").allowed is False

    def test_zero_rate_denies_everything(self):
        rl = RateLimiter(rate=0)
        assert rl.allow("k").allowed is False

    def test_check_does_not_consume(self):
        rl = RateLimiter(rate=1)
        assert rl.check("k").allowed is True
        assert rl.check("k").allowed is True  # still allowed, nothing consumed
        assert rl.allow("k").allowed is True
        assert rl.check("k").allowed is False


# ---------------------------------------------------------------------------
# 3. Runaway detection
# ---------------------------------------------------------------------------

class TestRunawayGuard:
    def test_repetition_detected(self):
        g = RunawayGuard(max_repeats=3)
        assert g.record("retry", "same") is None
        assert g.record("retry", "same") is None
        finding = g.record("retry", "same")
        assert finding is not None and finding.kind == "repetition"

    def test_distinct_actions_not_flagged(self):
        g = RunawayGuard(max_repeats=3)
        for i in range(10):
            assert g.record(f"action{i}") is None

    def test_cycle_detected(self):
        g = RunawayGuard(cycle_len=2)
        assert g.record("A") is None
        assert g.record("B") is None
        assert g.record("A") is None
        finding = g.record("B")
        assert finding is not None and finding.kind == "cycle"

    def test_no_progress_detected(self):
        g = RunawayGuard(max_same_progress=3)
        assert g.record("a", progress="p") is None
        assert g.record("b", progress="p") is None
        # the max_same_progress-th identical marker is the flag
        finding = g.record("c", progress="p")
        assert finding is not None and finding.kind == "no_progress"

    def test_progress_clears_no_progress(self):
        g = RunawayGuard(max_same_progress=3)
        g.record("a", progress="p")
        g.record("b", progress="p")
        g.record("c", progress="q")
        assert g.record("d", progress="r") is None

    def test_reset_clears_window(self):
        g = RunawayGuard(max_repeats=3)
        g.record("x", "s")
        g.record("x", "s")
        g.reset()
        assert g.record("x", "s") is None


# ---------------------------------------------------------------------------
# 4. Bounded failover
# ---------------------------------------------------------------------------

class TestFailover:
    def test_next_candidate_preserves_order(self):
        fc = FailoverChain()
        fc.add("a", "p1")
        fc.add("b", "p2")
        assert fc.next_candidate().name == "a"

    def test_unhealthy_candidate_is_skipped(self):
        fc = FailoverChain(failure_threshold=2, cooldown_seconds=100, clock=Clock())
        fc.add("a", "p1")
        fc.add("b", "p2")
        fc.report("a", False)
        fc.report("a", False)
        assert fc.next_candidate().name == "b"

    def test_cooldown_expires(self):
        clock = Clock()
        fc = FailoverChain(failure_threshold=1, cooldown_seconds=30, clock=clock)
        fc.add("a", "p1")
        fc.add("b", "p2")
        fc.report("a", False)
        assert fc.next_candidate().name == "b"
        clock.advance(31)
        assert fc.next_candidate().name == "a"

    def test_success_clears_failures(self):
        fc = FailoverChain(failure_threshold=3, clock=Clock())
        c = fc.add("a", "p1")
        fc.report("a", False)
        fc.report("a", False)
        fc.report("a", True)
        assert c.failures == 0 and c.healthy is True

    def test_plan_is_bounded(self):
        fc = FailoverChain(max_attempts=2)
        for name in "abcde":
            fc.add(name, name)
        assert [c.name for c in fc.plan()] == ["a", "b"]

    def test_no_healthy_candidate_returns_none(self):
        fc = FailoverChain(failure_threshold=1, cooldown_seconds=100, clock=Clock())
        fc.add("a", "p1")
        fc.report("a", False)
        assert fc.next_candidate() is None

    def test_unknown_candidate_report_raises(self):
        fc = FailoverChain()
        with pytest.raises(KeyError):
            fc.report("nope", False)


# ---------------------------------------------------------------------------
# 5. Resource governor / degraded modes
# ---------------------------------------------------------------------------

class TestGovernor:
    def test_normal_when_healthy(self):
        assert _governor(10, 20, 30).evaluate().mode == "normal"

    def test_strictest_breach_wins(self):
        # cpu halts, memory only reduced -> halted wins
        state = _governor(99, 80, 10).evaluate()
        assert state.mode == "halted"

    def test_each_mode(self):
        t = Thresholds()
        assert _governor(t.reduced_cpu + 1, 0, 0).evaluate().mode == "reduced"
        assert _governor(t.minimal_cpu + 1, 0, 0).evaluate().mode == "minimal"
        assert _governor(t.halted_cpu + 0.5, 0, 0).evaluate().mode == "halted"

    def test_failed_reading_fails_toward_caution(self):
        gov = ResourceGovernor(sampler=lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert gov.evaluate().mode == "reduced"

    def test_permits_matrix(self):
        assert ResourceGovernor.permits("halted", "essential") is True
        assert ResourceGovernor.permits("halted", "standard") is False
        assert ResourceGovernor.permits("reduced", "standard") is True
        assert ResourceGovernor.permits("reduced", "optional") is False
        assert ResourceGovernor.permits("normal", "optional") is True
        assert ResourceGovernor.permits("normal", "unknown-kind") is False


# ---------------------------------------------------------------------------
# 6. The gate
# ---------------------------------------------------------------------------

class TestBoundedAutonomyGate:
    def test_allows_within_bounds(self):
        auto = _autonomy()
        decision = auto.authorize("a", "chat", cost_usd=0.01, tokens=10)
        assert decision.allowed is True and decision.mode == "normal"

    def test_kill_switch_blocks(self):
        ks = LocalKillSwitch()
        ks.engage("incident")
        auto = _autonomy(kill_switch=ks)
        decision = auto.authorize("a", "chat")
        assert decision.allowed is False and "kill switch" in decision.reason

    def test_budget_blocks_and_is_free(self):
        ledger = BudgetLedger(default_limits=BudgetLimits(cost_usd=0.10, tokens=1000, requests=100,
                                                          tool_calls=100, wall_seconds=1000))
        auto = _autonomy(budgets=ledger, limiter=RateLimiter(rate=1000))
        auto.authorize("a", "chat", signature="1", cost_usd=0.08)
        denied = auto.authorize("a", "chat", signature="2", cost_usd=0.08)
        assert denied.allowed is False and "budget exceeded" in denied.reason
        assert ledger.for_scope("a").cost_usd == pytest.approx(0.08)  # refusal cost nothing

    def test_rate_limit_blocks(self):
        auto = _autonomy(limiter=RateLimiter(rate=2, window_seconds=60))
        assert auto.authorize("a", "x").allowed is True
        assert auto.authorize("a", "y").allowed is True
        denied = auto.authorize("a", "z")
        assert denied.allowed is False and "rate limit" in denied.reason

    def test_refused_action_does_not_consume_rate(self):
        auto = _autonomy(limiter=RateLimiter(rate=1, window_seconds=60),
                         budgets=BudgetLedger(default_limits=BudgetLimits(cost_usd=0.0)))
        # budget refuses (zero cost allowance); the rate slot must remain free
        assert auto.authorize("a", "x", cost_usd=0.01).allowed is False
        assert auto.limiter.check("a").remaining == 1

    def test_runaway_blocks(self):
        auto = _autonomy(limiter=RateLimiter(rate=1000))
        for i in range(2):
            assert auto.authorize("a", "loop", signature="same").allowed is True
        denied = auto.authorize("a", "loop", signature="same")
        assert denied.allowed is False and "runaway" in denied.reason and denied.runaway["kind"] == "repetition"

    def test_degraded_mode_blocks_optional_but_allows_essential(self):
        auto = _autonomy(governor=_governor(99, 20, 30))
        assert auto.authorize("a", "x", work="optional").allowed is False
        assert auto.authorize("a", "x", work="essential").allowed is True

    def test_scopes_are_isolated(self):
        ledger = BudgetLedger(default_limits=BudgetLimits(cost_usd=0.05, tokens=1000, requests=100,
                                                          tool_calls=100, wall_seconds=1000))
        auto = _autonomy(budgets=ledger, limiter=RateLimiter(rate=1000))
        assert auto.authorize("a", "x", cost_usd=0.05).allowed is True
        assert auto.authorize("a", "x", cost_usd=0.05).allowed is False
        assert auto.authorize("b", "x", cost_usd=0.05).allowed is True

    def test_status_shape(self):
        auto = _autonomy()
        status = auto.status()
        assert set(status) == {"kill_switch", "mode", "budgets", "rate", "failover"}

    def test_cost_recorded_in_canonical_tracker(self):
        recorded = []

        class Tracker:
            def track(self, provider, tokens, cost, model=""):
                recorded.append((provider, tokens, cost, model))

        auto = _autonomy(cost_tracker=Tracker(), limiter=RateLimiter(rate=1000))
        auto.authorize("a", "chat", cost_usd=0.02, tokens=7)
        assert recorded and recorded[0][1] == 7 and recorded[0][2] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# 7. Safety invariants
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    def test_unknown_scope_gets_bounded_default_not_unlimited(self):
        auto = _autonomy(budgets=BudgetLedger(default_limits=BudgetLimits(cost_usd=0.01)))
        assert auto.authorize("mystery", "x", cost_usd=1.0).allowed is False

    def test_gate_exposes_no_way_to_widen_limits(self):
        auto = _autonomy()
        public = [n for n in dir(auto) if not n.startswith("_")]
        assert not any("grant" in n or "escalate" in n or "unlimit" in n for n in public)

    def test_failover_never_retries_forever(self):
        fc = FailoverChain(max_attempts=2)
        for name in "abcd":
            fc.add(name, name)
        assert len(fc.plan()) == 2

    def test_zero_budget_scope_denies_all(self):
        auto = _autonomy(budgets=BudgetLedger(default_limits=BudgetLimits(
            cost_usd=0.0, tokens=0, requests=0, tool_calls=0, wall_seconds=0)))
        assert auto.authorize("a", "x").allowed is False

    def test_local_fallback_is_fail_closed_and_owner_gated(self):
        ks = LocalKillSwitch()
        assert ks.is_engaged() is False
        ks.engage("incident")
        assert ks.is_engaged() is True
        with pytest.raises(PermissionError):
            ks.disengage(owner_approved=False)  # a non-owner cannot resume autonomy
        ks.disengage(owner_approved=True, actor="owner")
        assert ks.is_engaged() is False

    def test_gate_resolves_canonical_switch_or_falls_back(self):
        # Resolution must never raise, so P8 imports without P6.
        from genesis_protocol.bounded import resolve_kill_switch

        switch = resolve_kill_switch()
        assert hasattr(switch, "is_engaged") and hasattr(switch, "status")
        # With no explicit switch, the gate picks up whatever resolved.
        assert _autonomy().kill_switch is not None
