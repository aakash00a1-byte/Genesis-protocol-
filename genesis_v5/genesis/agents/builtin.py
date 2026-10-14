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
    """Base for offline agents: produces deterministic outputs."""

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
        except Exception as exc:  # noqa: BLE001
            self.state = AgentState.FAILED
            return AgentResult(
                agent=self.name,
                task_id=task.id,
                status=AgentState.FAILED,
                error=str(exc),
            )
        self.state = AgentState.SUCCESS
        return AgentResult(
            agent=self.name,
            task_id=task.id,
            status=AgentState.SUCCESS,
            output=output,
            confidence=0.9,
            metadata={"duration_ms": int((time.time() - start) * 1000)},
        )

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
        GenericAgent,
    ]
    for cls in agents:
        # Register a fresh instance per request via a builder.
        registry.register(cls.name, lambda cls=cls: cls())