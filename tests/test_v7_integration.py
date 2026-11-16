"""Cross-phase integration tests for the V7 stack (P6-P10 + diagnostics).

These exercise the phases *together* on real code paths, using the canonical
subsystems (policy, identity registry, kill switch, security log, survival
monitor) rather than reimplementing them. They complement the per-phase suites,
which test each phase in isolation.
"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from genesis_protocol.agentic.identity_registry import IdentityRegistry  # noqa: E402
from genesis_protocol.bounded.autonomy import BoundedAutonomy  # noqa: E402
from genesis_protocol.bounded.budget import BudgetLedger, BudgetLimits  # noqa: E402
from genesis_protocol.bounded.emergency import LocalKillSwitch, resolve_kill_switch  # noqa: E402
from genesis_protocol.bounded.governor import ResourceGovernor as BoundedGovernor  # noqa: E402
from genesis_protocol.bounded.governor import ResourceReading  # noqa: E402
from genesis_protocol.bounded.ratelimit import RateLimiter  # noqa: E402
from genesis_protocol.bounded.runaway import RunawayGuard  # noqa: E402
from genesis_protocol.diagnostics import Diagnostics  # noqa: E402
from genesis_protocol.diagnostics.checks import STATUS_OK  # noqa: E402
from genesis_protocol.guardian.actionsink import LocalActionSink  # noqa: E402
from genesis_protocol.guardian.budget import ActionBudget  # noqa: E402
from genesis_protocol.guardian.defence import DefenceEngine  # noqa: E402
from genesis_protocol.guardian.events import SecurityEventLog  # noqa: E402
from genesis_protocol.guardian.killswitch import KillSwitch, get_kill_switch  # noqa: E402
from genesis_protocol.mission.manager import MissionManager  # noqa: E402
from genesis_protocol.mission.resources import ResourceBudget, ResourceGovernor  # noqa: E402
from genesis_protocol.mission.verification import ResultVerifier  # noqa: E402


class _Monitor:
    """Minimal resource monitor matching survival.resource_monitor's shape."""

    def __init__(self, reading):
        self._reading = reading

    def snapshot(self):
        return self._reading


class _Cost:
    def __init__(self, total):
        self._total = total

    def total(self):
        return self._total

    def get_total(self):
        return self._total


# ---------------------------------------------------------------------------
# P8 shares the canonical P6 emergency stop
# ---------------------------------------------------------------------------

class TestEmergencyStopIsShared:
    def test_bounded_resolves_the_canonical_kill_switch(self):
        assert type(resolve_kill_switch()).__name__ == "KillSwitch"
        assert resolve_kill_switch() is get_kill_switch()

    def test_engaging_kill_switch_stops_bounded_autonomy(self):
        ks = KillSwitch(":memory:")
        auto = BoundedAutonomy(kill_switch=ks)
        assert auto.authorize("scope", "chat").allowed is True
        ks.engage(reason="incident", actor="owner")
        decision = auto.authorize("scope", "chat")
        assert decision.allowed is False
        assert "kill" in (decision.reason or "").lower()

    def test_only_owner_may_disengage(self):
        ks = KillSwitch(":memory:")
        ks.engage(reason="x", actor="owner")
        with pytest.raises(PermissionError):
            ks.disengage(owner_approved=False)
        ks.disengage(owner_approved=True, actor="owner")
        assert ks.is_engaged() is False

    def test_local_fallback_is_fail_closed_when_absent(self):
        ks = LocalKillSwitch()
        assert ks.is_engaged() is False  # fresh local switch: not engaged
        ks.engage(reason="x")
        assert ks.is_engaged() is True


# ---------------------------------------------------------------------------
# P10 mission execution, bounded replanning, delegation, verification
# ---------------------------------------------------------------------------

def _mission_manager(tmpdir, registry=None, cpu=5, mem=10, cost=0.0, policy=None):
    return MissionManager(
        delegation=None if registry is None else __import__(
            "genesis_protocol.mission.delegation", fromlist=["DelegationManager"]
        ).DelegationManager(registry=registry),
        resources=ResourceGovernor(
            monitor=_Monitor({"cpu": {"percent": cpu}, "memory": {"percent": mem},
                              "disk": {"percent": 20}}),
            cost_tracker=_Cost(cost),
        ),
        verifier=ResultVerifier(),
        audit=None,
        policy=policy,
    )


class TestMissionExecution:
    def test_owner_approval_and_runner_required(self):
        mgr = _mission_manager(None)
        m = mgr.create_mission("one", owner_id=1)
        from genesis_protocol.mission.manager import MissionRefused
        with pytest.raises(MissionRefused):
            mgr.run_mission(m, lambda t: {"success": True}, owner_approved=False)
        with pytest.raises(MissionRefused):
            mgr.run_mission(m, None, owner_approved=True)

    def test_mission_completes_and_records_steps(self):
        mgr = _mission_manager(None)
        m = mgr.create_mission("one; two; three", owner_id=1, acceptance="done",
                               budget=ResourceBudget(max_steps=10))
        out = mgr.run_mission(m, lambda t: {"success": True, "summary": "done"},
                              owner_approved=True)
        assert out["status"] == "complete"
        assert out["progress"]["percent"] == 100.0

    def test_bounded_replanning_stops_a_runaway_task(self):
        mgr = _mission_manager(None)
        m = mgr.create_mission("one", owner_id=1, budget=ResourceBudget(max_steps=100))
        out = mgr.run_mission(m, lambda t: {"success": False}, owner_approved=True,
                              max_replans=3)
        assert out["replans_used"] == 3
        assert out["status"] == "needs_attention"
        assert out["steps_used"] == 4  # 1 original + 3 recovery attempts

    def test_delegation_cannot_exceed_the_agent_grant(self):
        reg = IdentityRegistry(":memory:")
        reg.register(name="worker", role="agent", owner_id=1,
                     tools=["calculator", "notes"], owner_approved=True)
        identity = reg.list_agents()[0]
        mgr = _mission_manager(None, registry=reg)
        m = mgr.create_mission("one", owner_id=1)
        task_id = m.tasks[0].task_id
        # within grant -> allowed
        mgr.delegate_task(m, task_id, identity.agent_id, tools=["calculator"])
        # beyond grant -> refused
        from genesis_protocol.mission.delegation import DelegationRefused
        with pytest.raises(DelegationRefused):
            mgr.delegate_task(m, task_id, identity.agent_id, tools=["deploy"])

    def test_delegation_refused_for_unregistered_agent(self):
        reg = IdentityRegistry(":memory:")
        mgr = _mission_manager(None, registry=reg)
        m = mgr.create_mission("one", owner_id=1)
        from genesis_protocol.mission.delegation import DelegationRefused
        with pytest.raises(DelegationRefused):
            mgr.delegate_task(m, m.tasks[0].task_id, "ghost", tools=[])


# ---------------------------------------------------------------------------
# P9 self-evolution stays propose-only and reversible
# ---------------------------------------------------------------------------

class TestEvolutionRestrictions:
    def test_engine_exposes_no_merge_deploy_apply(self):
        from genesis_protocol.evolution.engine import EvolutionEngine
        for forbidden in ("merge", "deploy", "approve", "apply_to_repo", "push"):
            assert not hasattr(EvolutionEngine, forbidden), forbidden

    def test_reversible_change_rolls_back_to_prior_bytes(self, tmp_path):
        from genesis_protocol.evolution.reversible import ReversibleChange
        target = tmp_path / "mod.py"
        target.write_text("VALUE = 1\n")
        change = ReversibleChange(change_id="c1",
                                  before={"mod.py": "VALUE = 1\n"},
                                  after={"mod.py": "VALUE = 2\n"})
        change.apply(str(tmp_path), owner_approved=True)
        assert target.read_text() == "VALUE = 2\n"
        change.rollback(str(tmp_path))
        assert target.read_text() == "VALUE = 1\n"


# ---------------------------------------------------------------------------
# P8 bounded autonomy: refused-is-free, kill switch wins, budget enforced
# ---------------------------------------------------------------------------

class TestBoundedAutonomyIntegration:
    def _auto(self, **kw):
        kw.setdefault("kill_switch", LocalKillSwitch())
        kw.setdefault("governor", BoundedGovernor(sampler=lambda: ResourceReading(10.0, 20.0, 30.0)))
        return BoundedAutonomy(**kw)

    def test_budget_refusal_is_free(self):
        limits = BudgetLimits(cost_usd=0.05)
        ledger = BudgetLedger(default_limits=limits)
        auto = self._auto(budgets=ledger)
        assert auto.authorize("s", "a", signature="1", cost_usd=0.03).allowed is True
        denied = auto.authorize("s", "a", signature="2", cost_usd=0.10)
        assert denied.allowed is False
        # the refused call must not have consumed budget
        assert auto.authorize("s", "a", signature="3", cost_usd=0.02).allowed is True

    def test_rate_limit_denies_beyond_window(self):
        auto = self._auto(limiter=RateLimiter(rate=2, window_seconds=60))
        assert auto.authorize("s", "a").allowed is True
        assert auto.authorize("s", "a").allowed is True
        assert auto.authorize("s", "a").allowed is False

    def test_runaway_guard_stops_repetition(self):
        auto = self._auto()
        for _ in range(3):
            auto.authorize("s", "loop", signature="same")
        assert auto.authorize("s", "loop", signature="same").allowed is False

    def test_governor_halts_on_resource_breach(self):
        gov = BoundedGovernor(sampler=lambda: ResourceReading(99.0, 99.0, 99.0))
        auto = self._auto(governor=gov)
        assert auto.authorize("s", "a", work="optional").allowed is False


# ---------------------------------------------------------------------------
# Diagnostics see the integrated phases as healthy
# ---------------------------------------------------------------------------

class TestDiagnosticsSeeIntegratedPhases:
    def test_diagnostics_healthy_on_integrated_branch(self):
        report = Diagnostics().run()
        payload = report.to_dict()
        assert payload["healthy"] is True
        by_name = {c["name"]: c["status"] for c in payload["results"]}
        for name in ("policy_fails_closed", "identity_fails_closed",
                     "audit_available", "recovery_available",
                     "evolution_propose_only", "mission_no_privileged_path",
                     "resources_readable", "observability_available"):
            assert by_name.get(name) == STATUS_OK, (name, by_name.get(name))
