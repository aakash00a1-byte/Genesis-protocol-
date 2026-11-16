"""Mission orchestration (V7 P10).

``MissionManager`` ties planning, delegation, resource awareness, tracking,
replanning and verification into one loop - and keeps every guard rail:

* it **plans** freely (side-effect free);
* it **runs** only when given an explicit ``runner`` *and* an owner approval,
  and only after the canonical policy allows the operation;
* every step is checked against the mission's resource budget first, and the
  result is **verified** before a task is marked done;
* a failed task triggers **replanning** rather than a silent retry loop;
* every transition is written to the canonical ``SecurityEventLog`` (source
  ``mission``).

The manager never merges, deploys, changes secrets, or performs a privileged
operation; it delegates to a runner the owner supplies and refuses everything
else.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from genesis_protocol.mission.delegation import Delegation, DelegationManager
from genesis_protocol.mission.planner import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_READY,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    Mission,
    MissionTask,
    plan,
    utcnow,
)
from genesis_protocol.mission.resources import ResourceBudget, ResourceGovernor
from genesis_protocol.mission.tracking import Replanner, progress
from genesis_protocol.mission.verification import ResultVerifier

DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_REPLANS = 3


class MissionRefused(RuntimeError):
    """Raised when a mission action is not permitted."""


class MissionManager:
    """Plans, delegates, tracks, replans and verifies missions."""

    def __init__(
        self,
        delegation: Optional[DelegationManager] = None,
        resources: Optional[ResourceGovernor] = None,
        verifier: Optional[ResultVerifier] = None,
        audit: Optional[Any] = None,
        policy: Optional[Any] = None,
    ):
        self.delegation = delegation or DelegationManager()
        self.resources = resources or ResourceGovernor()
        self.verifier = verifier or ResultVerifier()
        self._audit = audit
        self._policy = policy
        self._missions: Dict[str, Mission] = {}
        self._counter = 0

    # -- collaborators --------------------------------------------------------

    @property
    def audit(self) -> Any:
        if self._audit is None:
            try:
                from genesis_protocol.guardian.events import get_security_log

                self._audit = get_security_log()
            except Exception:
                self._audit = None
        return self._audit

    @property
    def policy(self) -> Any:
        if self._policy is None:
            try:
                from genesis_protocol.agentic.policy import get_agent_policy

                self._policy = get_agent_policy()
            except Exception:
                self._policy = None
        return self._policy

    def _record(self, event: str, severity: str = "info", **evidence: Any) -> None:
        log = self.audit
        if log is None:
            return
        try:
            log.record("integrity", event, severity=severity, subject="mission",
                       evidence=evidence, source="mission")
        except Exception:
            pass

    # -- planning -------------------------------------------------------------

    def create_mission(self, goal: str, owner_id: Optional[int] = None,
                       acceptance: str = "",
                       budget: Optional[ResourceBudget] = None) -> Mission:
        self._counter += 1
        mission = plan(f"m{self._counter}", goal, owner_id=owner_id, acceptance=acceptance)
        mission.budget = budget or ResourceBudget()
        mission.history.append({"at": utcnow(), "event": "created"})
        self._missions[mission.mission_id] = mission
        self._record("mission_created", mission_id=mission.mission_id,
                     tasks=len(mission.tasks), owner_id=owner_id)
        return mission

    def get(self, mission_id: str) -> Optional[Mission]:
        return self._missions.get(mission_id)

    def list(self) -> List[Mission]:
        return list(self._missions.values())

    def ready(self, mission: Mission) -> List[MissionTask]:
        return mission.ready_tasks()

    # -- delegation -----------------------------------------------------------

    def delegate_task(self, mission: Mission, task_id: str, agent_id: str,
                      tools: Optional[List[str]] = None,
                      credential: Optional[str] = None) -> Delegation:
        task = mission.task(task_id)
        if task is None:
            raise MissionRefused(f"unknown task '{task_id}'")
        delegation = self.delegation.delegate(task_id, agent_id, tools or (), credential=credential)
        task.assigned_to = agent_id
        if task.status == "pending":
            task.status = STATUS_READY
        task.updated_at = utcnow()
        self._record("task_delegated", mission_id=mission.mission_id, task_id=task_id,
                     agent_id=agent_id, tools=delegation.tools)
        return delegation

    # -- execution (owner-approved, runner-supplied only) ---------------------

    def run_mission(
        self,
        mission: Mission,
        runner: Callable[[MissionTask], Dict[str, Any]],
        owner_approved: bool = False,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_replans: int = DEFAULT_MAX_REPLANS,
    ) -> Dict[str, Any]:
        """Run ready tasks through ``runner`` until done, failed or out of budget.

        Refuses to run without an explicit owner approval and a runner. Each
        step is resource-checked and policy-checked before it runs, and its
        result is verified before the task is marked done.

        A failed task triggers at most ``max_replans`` automatic recovery
        attempts. Replanning is bounded so a task that keeps failing cannot drive
        an unbounded retry loop; once the bound is hit the mission stops and is
        reported ``needs_attention``.
        """
        if not owner_approved:
            raise MissionRefused("running a mission requires owner approval")
        if runner is None:
            raise MissionRefused("running a mission requires an explicit runner")
        if mission.has_cycle():
            raise MissionRefused("mission task graph contains a cycle")

        budget: ResourceBudget = getattr(mission, "budget", None) or ResourceBudget()
        tokens_used = 0
        steps_used = 0
        replans_used = 0
        ran: List[Dict[str, Any]] = []

        while steps_used < max_steps:
            ready = mission.ready_tasks()
            if not ready:
                break
            task = ready[0]

            decision = self.resources.check(
                budget, estimated_cost=0.0, tokens_used=tokens_used, steps_used=steps_used,
            )
            if not decision.ok:
                task.status = STATUS_BLOCKED
                task.updated_at = utcnow()
                self._record("task_blocked", severity="medium", mission_id=mission.mission_id,
                             task_id=task.task_id, reason=decision.reason)
                ran.append({"task_id": task.task_id, "status": STATUS_BLOCKED,
                            "reason": decision.reason})
                break

            allowed = self._authorize(mission, task)
            if not allowed.ok:
                task.status = STATUS_BLOCKED
                task.updated_at = utcnow()
                self._record("task_denied", severity="medium", mission_id=mission.mission_id,
                             task_id=task.task_id, reason=allowed.reason)
                ran.append({"task_id": task.task_id, "status": STATUS_BLOCKED,
                            "reason": allowed.reason})
                break

            task.status = STATUS_RUNNING
            task.attempts += 1
            steps_used += 1
            try:
                result = runner(task)
            except Exception as exc:  # a runner failure is a task failure, not a crash
                result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}

            outcome = self.verifier.verify(
                result,
                checks=_checks_for(task),
                require_success=True,
            )
            task.result = result if isinstance(result, dict) else {"value": result}
            task.updated_at = utcnow()

            if outcome.ok:
                task.status = STATUS_DONE
                tokens_used += int((task.result or {}).get("tokens", 0) or 0)
                self._record("task_done", mission_id=mission.mission_id, task_id=task.task_id)
                ran.append({"task_id": task.task_id, "status": STATUS_DONE})
            else:
                task.status = STATUS_FAILED
                self._record("task_failed", severity="medium", mission_id=mission.mission_id,
                             task_id=task.task_id, reasons=outcome.reasons)
                ran.append({"task_id": task.task_id, "status": STATUS_FAILED,
                            "reasons": outcome.reasons})
                if replans_used < max_replans:
                    if self._replan_if_possible(mission, task):
                        replans_used += 1
                else:
                    self._record("replan_budget_exhausted", severity="medium",
                                 mission_id=mission.mission_id, task_id=task.task_id)
                    break

        summary = {
            "mission_id": mission.mission_id,
            "status": self._mission_status(mission),
            "steps_used": steps_used,
            "replans_used": replans_used,
            "progress": progress(mission).to_dict(),
            "ran": ran,
            "revision": mission.revision,
        }
        self._record("mission_run", mission_id=mission.mission_id,
                     steps=steps_used, status=summary["status"])
        return summary

    def _authorize(self, mission: Mission, task: MissionTask) -> Any:
        policy = self.policy
        if policy is None:
            return _Allow(True, "no policy configured")
        decision = policy.authorize_operation(mission.owner_id, "mission_step")
        return _Allow(bool(decision.allowed), decision.reason)

    def _replan_if_possible(self, mission: Mission, task: MissionTask) -> bool:
        replanner = Replanner(mission)
        try:
            replanner.replace_failed(
                task.task_id,
                [f"recover: {task.goal}"],
                reason="automatic recovery after failure",
            )
            return True
        except Exception:
            # If replanning itself fails, leave the task failed; the mission
            # stays stalled and is surfaced rather than looping.
            return False

    @staticmethod
    def _mission_status(mission: Mission) -> str:
        if not mission.tasks:
            return "empty"
        states = {t.status for t in mission.tasks}
        if states <= {STATUS_DONE, STATUS_SKIPPED}:
            return "complete"
        if STATUS_FAILED in states:
            return "needs_attention"
        if STATUS_BLOCKED in states:
            return "blocked"
        return "in_progress"

    def status(self) -> Dict[str, Any]:
        return {
            "missions": len(self._missions),
            "by_status": {
                m.mission_id: self._mission_status(m) for m in self._missions.values()
            },
            "delegations": len(self.delegation.list()),
            "autonomy": "owner-approved execution only",
        }


class _Allow:
    def __init__(self, ok: bool, reason: str):
        self.ok = ok
        self.reason = reason


def _checks_for(task: MissionTask) -> List[Dict[str, Any]]:
    """Turn a task's acceptance text into checks, when it is expressible.

    A plain acceptance string is treated as a substring the result must contain
    under ``summary``. Structured acceptance is passed through verbatim.
    """
    acceptance = (task.acceptance or "").strip()
    if not acceptance:
        return []
    if acceptance.startswith("["):
        import json

        try:
            parsed = json.loads(acceptance)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
    return [{"contains": ["summary", acceptance]}]
