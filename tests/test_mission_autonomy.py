"""Contract tests for mission-level autonomy (V7 P10).

Covers mission planning, task decomposition, secure agent delegation, progress
tracking, replanning, resource awareness and result verification - plus the
safety invariants: execution needs an explicit owner approval and a supplied
runner, verification fails closed, delegation can only narrow a grant, and
unreadable resources are treated as a breach.
"""
from __future__ import annotations

import pytest

from genesis_protocol.mission import (
    DelegationManager,
    DelegationRefused,
    MissionManager,
    MissionRefused,
    ResourceBudget,
    ResourceGovernor,
    ResultVerifier,
    decompose,
    plan,
    progress,
)
from genesis_protocol.mission.tracking import Replanner


# ---------------------------------------------------------------------------
# 1. Planning and decomposition
# ---------------------------------------------------------------------------

class TestPlanning:
    def test_decompose_splits_clauses_and_chains(self):
        tasks = decompose("gather data; analyze it; write the report")
        assert [t["task_id"] for t in tasks] == ["t1", "t2", "t3"]
        assert tasks[0]["depends_on"] == []
        assert tasks[1]["depends_on"] == ["t1"]
        assert tasks[2]["depends_on"] == ["t2"]

    def test_decompose_honours_after_marker(self):
        tasks = decompose("a; b; after: t1 - c")
        assert tasks[2]["depends_on"] == ["t1"]

    def test_decompose_requires_a_goal(self):
        with pytest.raises(ValueError):
            decompose("   ")

    def test_plan_builds_a_dag_with_no_cycle(self):
        mission = plan("m1", "one; two; three")
        assert mission.has_cycle() is False
        assert len(mission.tasks) == 3

    def test_plan_rejects_unknown_dependency(self):
        with pytest.raises(ValueError):
            plan("m1", "after: tX - do it")

    def test_ready_tasks_respect_dependencies(self):
        mission = plan("m1", "one; two")
        assert [t.task_id for t in mission.ready_tasks()] == ["t1"]
        mission.tasks[0].status = "done"
        assert [t.task_id for t in mission.ready_tasks()] == ["t2"]


# ---------------------------------------------------------------------------
# 2. Progress tracking and replanning
# ---------------------------------------------------------------------------

class TestTracking:
    def test_progress_counts_and_percent(self):
        mission = plan("m1", "one; two")
        mission.tasks[0].status = "done"
        p = progress(mission)
        assert p.total == 2 and p.done == 1 and p.percent == 50.0

    def test_stalled_when_nothing_ready_and_work_remains(self):
        mission = plan("m1", "one; two")
        mission.tasks[0].status = "failed"
        mission.tasks[1].status = "blocked"
        assert progress(mission).stalled is True

    def test_replanner_replaces_failed_task_and_rewires_dependents(self):
        mission = plan("m1", "one; two; three")
        mission.tasks[0].status = "failed"
        created = Replanner(mission).replace_failed(
            "t1", ["retry one", "retry one again"], reason="test")
        assert [t.task_id for t in created] == ["t1r1", "t1r2"]
        assert mission.tasks[0].status == "skipped"
        # t2 now depends on the last replacement, not the failed task.
        assert mission.task("t2").depends_on == ["t1r2"]
        assert mission.revision == 1
        assert any(h["event"] == "replanned" for h in mission.history)

    def test_replanner_refuses_to_replace_a_done_task(self):
        mission = plan("m1", "one")
        mission.tasks[0].status = "done"
        with pytest.raises(ValueError):
            Replanner(mission).replace_failed("t1", ["x"])


# ---------------------------------------------------------------------------
# 3. Resource awareness
# ---------------------------------------------------------------------------

class _Monitor:
    def __init__(self, stats):
        self._stats = stats

    def get_all_stats(self):
        return self._stats


class _Cost:
    def __init__(self, today):
        self._today = today

    def get_today(self):
        return self._today


class TestResources:
    def _gov(self, cpu=5, mem=10, cost=0.0):
        return ResourceGovernor(
            monitor=_Monitor({"cpu": {"percent": cpu}, "memory": {"percent": mem},
                              "disk": {"percent": 20}}),
            cost_tracker=_Cost(cost),
        )

    def test_within_budget(self):
        decision = self._gov().check(ResourceBudget(max_cpu_percent=80, max_memory_percent=80))
        assert decision.ok is True

    def test_cpu_breach_refused(self):
        decision = self._gov(cpu=95).check(ResourceBudget(max_cpu_percent=80))
        assert decision.ok is False and "cpu" in decision.reason

    def test_step_budget_exhausted(self):
        decision = self._gov().check(ResourceBudget(max_steps=2), steps_used=2)
        assert decision.ok is False and "step budget" in decision.reason

    def test_token_budget_exhausted(self):
        decision = self._gov().check(ResourceBudget(max_tokens=10), tokens_used=10,
                                     estimated_tokens=5)
        assert decision.ok is False and "token budget" in decision.reason

    def test_cost_budget_exhausted(self):
        decision = self._gov(cost=9.5).check(ResourceBudget(max_cost=10.0), estimated_cost=1.0)
        assert decision.ok is False and "cost budget" in decision.reason

    def test_unreadable_monitor_fails_closed(self):
        gov = ResourceGovernor(monitor=None, cost_tracker=None)
        decision = gov.check(ResourceBudget(max_cpu_percent=80))
        # No monitor -> the snapshot is unreadable -> refuse when a limit is set.
        assert decision.ok is False and "unreadable" in decision.reason


# ---------------------------------------------------------------------------
# 4. Result verification (fail closed)
# ---------------------------------------------------------------------------

class TestVerification:
    def _v(self):
        return ResultVerifier()

    def test_success_required(self):
        assert self._v().verify({"success": False}).ok is False
        assert self._v().verify({"success": True}).ok is True

    def test_equals_and_contains_and_numeric(self):
        result = {"success": True, "status": "ok", "items": [1, 2, 3], "count": 3}
        checks = [{"equals": ["status", "ok"]}, {"contains": ["items", 2]},
                  {"min": ["count", 1]}, {"max": ["count", 5]}]
        assert self._v().verify(result, checks).ok is True

    def test_missing_field_fails_closed(self):
        outcome = self._v().verify({"success": True}, [{"truthy": ["nope"]}])
        assert outcome.ok is False and "missing field" in outcome.reasons[0]

    def test_unknown_operation_fails_closed(self):
        outcome = self._v().verify({"success": True}, [{"frobnicate": ["x"]}])
        assert outcome.ok is False and "unknown operation" in outcome.reasons[0]

    def test_nested_path_lookup(self):
        result = {"success": True, "data": {"items": [{"id": 7}]}}
        assert self._v().verify(result, [{"equals": ["data.items.0.id", 7]}]).ok is True

    def test_non_mapping_result_fails(self):
        assert self._v().verify("just a string").ok is False
        assert self._v().verify(None).ok is False


# ---------------------------------------------------------------------------
# 5. Delegation (narrow only, verify identity)
# ---------------------------------------------------------------------------

class _Identity:
    def __init__(self, agent_id, tools, status="active"):
        self.agent_id = agent_id
        self.tools = tuple(tools)
        self.status = status


class _Registry:
    def __init__(self, identities):
        self._by_id = {i.agent_id: i for i in identities}

    def get(self, agent_id):
        return self._by_id.get(agent_id)

    def verify(self, agent_id, credential=None):
        identity = self.get(agent_id)
        if identity is None:
            return type("V", (), {"ok": False, "reason": "unknown"})()

        class V:
            ok = identity.status == "active"
            reason = "verified" if ok else f"agent is {identity.status}"
        return V()


class TestDelegation:
    def _mgr(self, identities):
        return DelegationManager(registry=_Registry(identities))

    def test_delegation_to_verified_agent_succeeds(self):
        mgr = self._mgr([_Identity("a1", ["read", "search"])])
        delegation = mgr.delegate("t1", "a1", ["read"])
        assert delegation.agent_id == "a1" and delegation.tools == ["read"]

    def test_unknown_agent_refused(self):
        mgr = self._mgr([])
        with pytest.raises(DelegationRefused):
            mgr.delegate("t1", "ghost", ["read"])

    def test_suspended_agent_refused(self):
        mgr = self._mgr([_Identity("a1", ["read"], status="suspended")])
        with pytest.raises(DelegationRefused):
            mgr.delegate("t1", "a1", ["read"])

    def test_delegation_cannot_widen_agent_grant(self):
        mgr = self._mgr([_Identity("a1", ["read"])])
        with pytest.raises(DelegationRefused):
            mgr.delegate("t1", "a1", ["read", "deploy"])

    def test_delegation_cannot_exceed_delegator_grant(self):
        mgr = self._mgr([_Identity("parent", ["read"]), _Identity("child", ["read", "write"])])
        with pytest.raises(DelegationRefused):
            mgr.delegate("t1", "child", ["write"], delegator_id="parent")

    def test_no_registry_refuses(self):
        mgr = DelegationManager(registry=object())  # not a registry; no get/verify
        with pytest.raises(DelegationRefused):
            mgr.delegate("t1", "a1", [])

    def test_revoke(self):
        mgr = self._mgr([_Identity("a1", ["read"])])
        delegation = mgr.delegate("t1", "a1", ["read"])
        mgr.revoke(delegation.delegation_id, reason="done")
        assert mgr.list()[0].status == "revoked"


# ---------------------------------------------------------------------------
# 6. The manager loop
# ---------------------------------------------------------------------------

class TestManager:
    def _mgr(self, cpu=5, mem=10):
        return MissionManager(
            resources=ResourceGovernor(
                monitor=_Monitor({"cpu": {"percent": cpu}, "memory": {"percent": mem},
                                  "disk": {"percent": 20}}),
                cost_tracker=_Cost(0.0),
            ),
            audit=None,
        )

    def test_run_requires_owner_approval(self):
        mgr = self._mgr()
        mission = mgr.create_mission("one; two", owner_id=1)
        with pytest.raises(MissionRefused):
            mgr.run_mission(mission, lambda t: {"success": True}, owner_approved=False)

    def test_run_requires_a_runner(self):
        mgr = self._mgr()
        mission = mgr.create_mission("one", owner_id=1)
        with pytest.raises(MissionRefused):
            mgr.run_mission(mission, None, owner_approved=True)

    def test_run_completes_when_results_verify(self):
        mgr = self._mgr()
        mission = mgr.create_mission("one; two; three", owner_id=1, acceptance="done",
                                     budget=ResourceBudget(max_steps=10))
        out = mgr.run_mission(mission, lambda t: {"success": True, "summary": "done"},
                              owner_approved=True)
        assert out["status"] == "complete"
        assert out["progress"]["percent"] == 100.0

    def test_failed_result_triggers_replan(self):
        mgr = self._mgr()
        mission = mgr.create_mission("one", owner_id=1, acceptance="done",
                                     budget=ResourceBudget(max_steps=5))
        out = mgr.run_mission(mission, lambda t: {"success": True, "summary": "wrong"},
                              owner_approved=True)
        assert any(r["status"] == "failed" for r in out["ran"])
        assert mission.revision >= 1

    def test_replanning_is_bounded(self):
        # A task that always fails must not drive an unbounded retry loop.
        mgr = self._mgr()
        mission = mgr.create_mission("one", owner_id=1,
                                     budget=ResourceBudget(max_steps=100))
        out = mgr.run_mission(mission, lambda t: {"success": False}, owner_approved=True,
                              max_replans=3)
        assert out["replans_used"] == 3
        assert out["status"] == "needs_attention"
        # 1 original + 3 recovery attempts, then it stops.
        assert out["steps_used"] == 4

    def test_runner_exception_is_a_task_failure_not_a_crash(self):
        mgr = self._mgr()
        mission = mgr.create_mission("one", owner_id=1, budget=ResourceBudget(max_steps=5))
        out = mgr.run_mission(mission, lambda t: (_ for _ in ()).throw(RuntimeError("boom")),
                              owner_approved=True)
        assert out["status"] in {"needs_attention", "in_progress"}
        assert any(r["status"] == "failed" for r in out["ran"])

    def test_resource_breach_blocks_and_stops(self):
        mgr = self._mgr(cpu=99)
        mission = mgr.create_mission("one; two", owner_id=1,
                                     budget=ResourceBudget(max_cpu_percent=50, max_steps=5))
        out = mgr.run_mission(mission, lambda t: {"success": True}, owner_approved=True)
        assert out["ran"][0]["status"] == "blocked"

    def test_status_reports_owner_approved_execution(self):
        status = self._mgr().status()
        assert "owner-approved" in status["autonomy"]

    def test_manager_has_no_privileged_surface(self):
        mgr = self._mgr()
        exposed = {n for n in dir(mgr) if not n.startswith("_")}
        forbidden = {"merge", "deploy", "push", "publish", "set_secret", "grant_admin"}
        assert forbidden.isdisjoint(exposed)
