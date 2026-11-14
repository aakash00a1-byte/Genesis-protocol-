"""A real, bounded agent loop for GLUTEN.

Stages, in order, for every request:

    understand -> plan -> request tool -> policy check -> execute -> verify -> respond

Properties that make this more than a prompt wrapper:

* It executes through the existing ``ToolRegistry`` (real, configured tools) and
  the sandbox, not by asking the model to *pretend* to run something.
* Code *generation* and code *execution* are distinct step types. Generating
  code never runs it.
* Every tool request passes a fail-closed policy check; denied requests are
  recorded and never executed.
* Every step - allowed or denied, succeeded or failed - is appended to the
  task's history, so execution is inspectable after the fact.
* Failures are recovered per ``on_error`` and surfaced; nothing is reported as
  done unless its step actually succeeded.

The loop is driven by a caller. It is not a background daemon and does not
claim to be one.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.audit import AuditLog, get_audit_log
from genesis_protocol.agentic.memory import AgentMemory, get_agent_memory
from genesis_protocol.agentic.policy import AgentPolicy, get_agent_policy
from genesis_protocol.agentic.sandbox import run_python
from genesis_protocol.agentic.tasks import TaskStore, get_task_store

STEP_TYPES = {"tool", "skill", "generate_code", "execute_code", "respond"}

# A caller-supplied plan is capped so one request cannot occupy a worker
# indefinitely. The loop is synchronous, so an unbounded list is a cheap DoS.
MAX_STEPS = 50

# Tools that read or write per-user state. The authoritative ``user_id`` is
# injected server-side; any value the caller put in ``params`` is discarded so
# a user cannot read another user's data by passing a different id.
USER_SCOPED_TOOLS = {"memory_search", "history_search", "task_manager", "image_analyzer"}


class AgentLoop:
    def __init__(
        self,
        registry: Optional[Any] = None,
        memory: Optional[AgentMemory] = None,
        tasks: Optional[TaskStore] = None,
        policy: Optional[AgentPolicy] = None,
        audit: Optional[AuditLog] = None,
    ):
        self._registry = registry
        self.memory = memory or get_agent_memory()
        self.tasks = tasks or get_task_store()
        self.policy = policy or get_agent_policy()
        self.audit = audit or get_audit_log()

    @property
    def registry(self):
        if self._registry is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._registry = get_tool_registry()
        return self._registry

    # -- planning -------------------------------------------------------------

    def plan(self, goal: str, steps: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Return the steps to run.

        When the caller supplies steps they are used as-is (and validated),
        up to ``MAX_STEPS``. Otherwise a minimal, honest plan is produced: a
        single ``respond`` step. No fabricated tool calls are invented here.
        """
        if steps is not None:
            if len(steps) > MAX_STEPS:
                raise ValueError(f"too many steps: {len(steps)} (max {MAX_STEPS})")
            return [self._validate_step(s) for s in steps]
        return self._plan_from_goal(goal)

    def _plan_from_goal(self, goal: str) -> List[Dict[str, Any]]:
        """Plan real tool steps from the goal, or an empty plan.

        An empty plan is honest: it means no step could be planned, and the
        caller is told so rather than being handed a "completed" task that ran
        nothing. Only tools that exist in the registry are planned.
        """
        planned: List[Dict[str, Any]] = []

        try:
            available = {t.name for t in self.registry.get_all_tools()}
        except Exception:
            available = set()

        # Only safe, clearly-supported steps are planned automatically. Anything
        # needing a restricted tool (files, subprocess, network) is left to the
        # caller to specify explicitly, since it would otherwise be denied.
        match = re.search(r"[-+]?\d[\d\s.+\-*/()]*\d", goal or "")
        if match and "calculator" in available:
            planned.append({"type": "tool", "tool": "calculator",
                            "params": {"expression": match.group(0).strip()}})

        if planned:
            planned.append({"type": "respond", "goal": goal})
        return planned

    @staticmethod
    def _validate_step(step: Dict[str, Any]) -> Dict[str, Any]:
        stype = (step or {}).get("type")
        if stype not in STEP_TYPES:
            raise ValueError(f"unknown step type '{stype}' (allowed: {sorted(STEP_TYPES)})")
        if stype == "tool" and not step.get("tool"):
            raise ValueError("tool step requires a 'tool' name")
        if stype == "skill" and not step.get("skill"):
            raise ValueError("skill step requires a 'skill' name")
        if stype == "execute_code" and "code" not in step:
            raise ValueError("execute_code step requires 'code'")
        return step

    # -- execution ------------------------------------------------------------

    def run(
        self,
        user_id: int,
        goal: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None,
        owner_approved: bool = False,
        on_error: str = "stop",
    ) -> Dict[str, Any]:
        """Run the loop for ``goal``. Returns structured evidence."""
        planned = self.plan(goal, steps)

        if not planned:
            # No step could be planned. Report that plainly; do not create a
            # task that looks "completed" while nothing ran.
            return {
                "task_id": task_id,
                "user_id": int(user_id),
                "goal": goal,
                "state": "no_plan",
                "steps": [],
                "resumed_from": 0,
                "note": "no executable step could be planned from this goal; "
                        "supply explicit steps",
            }

        if task_id is None:
            task = self.tasks.create(user_id, goal)
            task_id = task.id
        else:
            existing = self.tasks.get(user_id, task_id)
            if existing is None:
                raise KeyError("task not found")
            task = existing

        start_index = self.tasks.resume_point(user_id, task_id) if task.steps else 0
        self.tasks.set_state(user_id, task_id, "running")

        results: List[Dict[str, Any]] = []
        failed = False

        for index, step in enumerate(planned):
            if index < start_index:
                continue  # resume: skip steps already completed in a prior run
            outcome = self._run_step(user_id, step, owner_approved)
            outcome["index"] = index
            self.tasks.append_step(user_id, task_id, outcome)
            results.append(outcome)
            if not outcome["success"]:
                failed = True
                if on_error == "stop":
                    break

        final_state = "failed" if failed else "completed"
        self.tasks.set_state(
            user_id, task_id, final_state, error=results[-1].get("error") if failed else None
        )

        return {
            "task_id": task_id,
            "user_id": int(user_id),
            "goal": goal,
            "state": final_state,
            "steps": results,
            "resumed_from": start_index,
        }

    def _run_step(self, user_id: int, step: Dict[str, Any], owner_approved: bool) -> Dict[str, Any]:
        stype = step["type"]
        if stype == "tool":
            return self._run_tool_step(user_id, step, owner_approved)
        if stype == "skill":
            return self._run_skill_step(user_id, step, owner_approved)
        if stype == "generate_code":
            return self._run_generate_code_step(user_id, step)
        if stype == "execute_code":
            return self._run_execute_code_step(user_id, step)
        return self._run_respond_step(user_id, step)

    def _run_tool_step(
        self, user_id: int, step: Dict[str, Any], owner_approved: bool
    ) -> Dict[str, Any]:
        name = step["tool"]
        params = dict(step.get("params", {}) or {})

        # Never trust a caller-supplied user_id: it is the key to another
        # user's memories and tasks. Drop it and bind the tool to the
        # authenticated user instead.
        if name in USER_SCOPED_TOOLS:
            params.pop("user_id", None)
            params["user_id"] = user_id

        tool = None
        try:
            tool = self.registry.get_tool(name)
        except Exception:
            tool = None

        if tool is None:
            decision = self.policy.authorize_tool(user_id, name, permission=None)
            self.audit.record("tool_request", user_id, name, False, decision.reason)
            return {
                "type": "tool",
                "tool": name,
                "success": False,
                "error": f"tool '{name}' is not available",
                "policy": decision.to_dict(),
                "denied": True,
            }

        perm = getattr(getattr(tool, "permission", None), "value", None)
        decision = self.policy.authorize_tool(user_id, name, permission=perm, owner_approved=owner_approved)
        self.audit.record(
            "tool_request", user_id, name, decision.allowed, decision.reason, detail=params
        )
        if not decision.allowed:
            return {
                "type": "tool",
                "tool": name,
                "success": False,
                "error": decision.reason,
                "policy": decision.to_dict(),
                "denied": True,
            }

        try:
            result = self.registry.execute(name, params)
        except Exception as exc:  # pragma: no cover - defensive
            result = {"success": False, "error": str(exc)}

        verified = self._verify_tool_result(result)
        self.audit.record(
            "tool_result", user_id, name, verified, "verified" if verified else "verification failed"
        )
        return {
            "type": "tool",
            "tool": name,
            "success": verified,
            "result": result,
            "policy": decision.to_dict(),
            "error": None if verified else result.get("error", "verification failed"),
        }

    def _run_skill_step(
        self, user_id: int, step: Dict[str, Any], owner_approved: bool
    ) -> Dict[str, Any]:
        """Run a skill through the tools it declares."""
        from genesis_protocol.agentic.skills import SkillRunner

        runner = SkillRunner(registry=self.registry, policy=self.policy, audit=self.audit)
        outcome = runner.run(
            user_id=user_id,
            skill_name=step["skill"],
            tool_params=step.get("tool_params", {}),
            owner_approved=owner_approved,
        )
        return {
            "type": "skill",
            "skill": step["skill"],
            "success": bool(outcome.get("success")),
            "executed": bool(outcome.get("executed")),
            "denied": bool(outcome.get("denied")),
            "result": outcome,
            "error": None if outcome.get("success") else outcome.get("error", "skill did not fully run"),
        }

    @staticmethod
    def _verify_tool_result(result: Any) -> bool:
        """A tool step succeeds only when the tool reports success."""
        return isinstance(result, dict) and bool(result.get("success"))

    def _run_generate_code_step(self, user_id: int, step: Dict[str, Any]) -> Dict[str, Any]:
        """Produce code text without executing it."""
        code = step.get("code", "")
        return {
            "type": "generate_code",
            "success": bool(code),
            "code": code,
            "executed": False,
            "note": "generated only; not executed",
        }

    def _run_execute_code_step(self, user_id: int, step: Dict[str, Any]) -> Dict[str, Any]:
        code = step["code"]
        self.audit.record("code_execution", user_id, tool="sandbox", allowed=True, reason="sandboxed")
        result = run_python(
            code,
            timeout=step.get("timeout", 5.0),
            memory_mb=step.get("memory_mb", 256),
            cpu_seconds=step.get("cpu_seconds", 5),
        )
        return {
            "type": "execute_code",
            "success": result.success,
            "executed": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "duration_ms": result.duration_ms,
            "limits": result.limits,
            "error": result.error,
        }

    def _run_respond_step(self, user_id: int, step: Dict[str, Any]) -> Dict[str, Any]:
        """Terminal step: the answer is produced elsewhere; record intent here."""
        return {
            "type": "respond",
            "success": True,
            "goal": step.get("goal", ""),
            "note": "response produced by the chat pipeline",
        }
