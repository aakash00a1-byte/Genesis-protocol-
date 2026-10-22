"""Built-in Genesis V5 agents.

All agents are offline-capable and operate through the Kernel's tool gateway
(via `Agent.request_tool`). They never execute real-world actions on their
own — the Kernel's permission/sandbox gates control every tool call.
"""
from __future__ import annotations

import time
from typing import Any

from genesis.core import new_id
from genesis.agents.base import Agent, AgentResult, AgentState, AgentTask


class _DeterministicAgent(Agent):
    """Base for offline agents: produces deterministic outputs.

    An agent may also carry one explicit tool request in the task metadata
    (``metadata={"tool": "file.list", "args": {...}}``). When a Kernel-mediated
    gateway is bound, the agent routes that request through it — the full
    policy/permission/sandbox/audit gate — and records the outcome. The agent
    still never executes anything itself. When no gateway is bound, or no tool
    was requested, behaviour is exactly as before.
    """

    name = "generic"
    description = "A deterministic offline agent."
    verb = "processed"
    _fail_keyword = "INJECT-FAILURE"

    def run(self, task: AgentTask) -> AgentResult:
        self.state = AgentState.RUNNING
        start = time.time()
        try:
            output = self._produce(task)
            if self._fail_keyword in str(task.instruction):
                output = f"{output}\nERROR: deliberate injected failure"
            tool_outcome = self._maybe_request_tool(task)
        except Exception as exc:  # noqa: BLE001
            self.state = AgentState.FAILED
            return AgentResult(
                agent=self.name,
                task_id=task.id,
                status=AgentState.FAILED,
                error=str(exc),
            )
        self.state = AgentState.SUCCESS
        metadata: dict[str, Any] = {"duration_ms": int((time.time() - start) * 1000)}
        if tool_outcome is not None:
            metadata["tool"] = tool_outcome
        return AgentResult(
            agent=self.name,
            task_id=task.id,
            status=AgentState.SUCCESS,
            output=output,
            confidence=0.9,
            metadata=metadata,
        )

    def _maybe_request_tool(self, task: AgentTask) -> dict[str, Any] | None:
        """Route a single, explicitly-declared tool request through the gate.

        The request comes from the task metadata, never from agent invention.
        With no gateway bound there is nothing to route through, so the agent
        reports that rather than executing anything.
        """
        tool = task.metadata.get("tool")
        if not tool:
            return None
        if self._tool_request is None:
            return {"tool": str(tool), "status": "no_gateway", "executed": False}
        result = self.request_tool(str(tool), dict(task.metadata.get("args", {})))
        status = getattr(result, "status", None)
        return {
            "tool": str(tool),
            "status": status.value if status is not None else None,
            "executed": bool(getattr(result, "ok", False)),
        }

    def _produce(self, task: AgentTask) -> Any:
        context = task.context.get("task", "")
        return f"[{self.verb}] {task.instruction[:120]}"


class CodingAgent(_DeterministicAgent):
    name = "coding"
    description = "Implements code changes within the sandbox."
    verb = "implemented"


class ResearchAgent(_DeterministicAgent):
    name = "research"
    description = "Gathers and summarizes information (offline stubs)."
    verb = "researched"


class PlanningAgent(_DeterministicAgent):
    name = "planning"
    description = "Produces a structured plan."
    verb = "planned"


class QAAgent(_DeterministicAgent):
    name = "qa"
    description = "Verifies results independently."
    verb = "verified"


class SecurityAgent(_DeterministicAgent):
    name = "security"
    description = "Reviews changes for security issues."
    verb = "security-reviewed"


class DeploymentAgent(_DeterministicAgent):
    name = "deployment"
    description = "Prepares deployment artifacts (never deploys)."
    verb = "prepared"


class MemoryAgent(_DeterministicAgent):
    name = "memory"
    description = "Persists and retrieves memory via the Kernel."
    verb = "memorized"


class EvolutionAgent(_DeterministicAgent):
    """Fallback evolution agent used by the registry/planner.

    The registry builds agents with no arguments, so this thin subclass only
    carries the name and label. The full self-observation implementation lives
    in ``genesis.evolution.evolution.EvolutionAgent`` and is wired explicitly
    (with a signal collector and store) by the bootstrap/runner.
    """

    name = "evolution"
    description = "Observes the system and proposes bounded improvements."
    verb = "proposed improvements for"


# A generic fallback for unassigned labels.
class GenericAgent(_DeterministicAgent):
    name = "generic"
    description = "Generic fallback agent."
    verb = "processed"


def register_builtin_agents(registry) -> None:
    agents = [
        CodingAgent,
        ResearchAgent,
        PlanningAgent,
        QAAgent,
        SecurityAgent,
        DeploymentAgent,
        MemoryAgent,
        EvolutionAgent,
        GenericAgent,
    ]
    for cls in agents:
        # Register a fresh instance per request via a builder.
        registry.register(cls.name, lambda cls=cls: cls())