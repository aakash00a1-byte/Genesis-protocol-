"""TaskDecomposer and Planner.

The decomposer splits a complex task into subtasks. The planner assigns each
subtask to an agent and records dependencies. Deterministic, offline
heuristics keep the system testable without a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from genesis.core import new_id
from genesis.providers.base import ModelCapability

from .graph import DependencyGraph


@dataclass
class PlanStep:
    id: str
    agent: str
    instruction: str
    dependencies: list[str] = field(default_factory=list)

    def is_root(self) -> bool:
        return not self.dependencies


@dataclass
class Plan:
    steps: list[PlanStep]
    graph: DependencyGraph = field(default_factory=DependencyGraph)

    def root_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.is_root()]


class TaskDecomposer:
    """Splits a complex task into labeled subtasks.

    Pure heuristic parsing so it works offline and is predictable in tests.
    """

    def decompose(self, task: str) -> list[dict[str, object]]:
        lowered = task.lower()
        subtasks: list[dict[str, object]] = []

        # Identify candidate sub-goals by domain keywords in the task text.
        if any(k in lowered for k in ["code", "implement", "function", "refactor"]):
            subtasks.append(
                {"label": "implement", "instruction": f"Implement the code for: {task}"}
            )
        if any(k in lowered for k in ["test", "verify", "qa"]):
            subtasks.append(
                {"label": "verify", "instruction": f"Verify the result of: {task}"}
            )
        if any(k in lowered for k in ["security", "permission", "audit", "threat"]):
            subtasks.append(
                {"label": "security", "instruction": f"Security-review: {task}"}
            )
        if any(k in lowered for k in ["plan", "design", "architecture"]):
            subtasks.append(
                {"label": "plan", "instruction": f"Plan the approach for: {task}"}
            )
        if any(k in lowered for k in ["research", "search", "investigate"]):
            subtasks.append(
                {"label": "research", "instruction": f"Research: {task}"}
            )
        if any(k in lowered for k in ["deploy", "release", "package"]):
            subtasks.append(
                {"label": "deploy", "instruction": f"Prepare deployment for: {task}"}
            )

        # Memory is always a candidate (gather context, persist outcome).
        subtasks.append(
            {"label": "memory", "instruction": f"Manage memory for: {task}"}
        )

        if not subtasks:
            subtasks.append(
                {"label": "implement", "instruction": task}
            )
            subtasks.append(
                {"label": "memory", "instruction": f"Manage memory for: {task}"}
            )
        return subtasks


_AGENT_BY_LABEL: dict[str, str] = {
    "implement": "coding",
    "verify": "qa",
    "security": "security",
    "plan": "planning",
    "research": "research",
    "deploy": "deployment",
    "memory": "memory",
}


class Planner:
    """Produces a dependency-ordered Plan of subtasks.

    The Kernel remains the authority; the planner only proposes. Dependencies:
    `plan` -> all -> `memory`, and `implement` -> `verify` -> `security`
    (when present). These are heuristics, deliberately simple and offline.
    """

    def __init__(
        self,
        decomposer: TaskDecomposer | None = None,
        agent_for: Callable[[str], str] | None = None,
    ) -> None:
        self.decomposer = decomposer or TaskDecomposer()
        self._agent_for = agent_for or (
            lambda label: _AGENT_BY_LABEL.get(label, "generic")
        )

    def plan(self, task: str, *, task_id: str | None = None, plan_id: str | None = None) -> Plan:
        base_id = plan_id or new_id("plan")
        subtasks = self.decomposer.decompose(task)

        steps: list[PlanStep] = []
        labels_seen: dict[str, PlanStep] = {}
        for index, sub in enumerate(subtasks):
            label = str(sub["label"])
            if label in labels_seen:
                continue
            step_id = f"{base_id}:{index}:{label}"
            step = PlanStep(
                id=step_id,
                agent=self._agent_for(label),
                instruction=str(sub["instruction"]),
            )
            steps.append(step)
            labels_seen[label] = step

        label_step = {s.agent: s for s in steps}
        # plan must precede everything else (if present)
        if "planning" in label_step:
            plan_step = label_step["planning"]
            for step in steps:
                if step is not plan_step:
                    step.dependencies.append(plan_step.id)

        # implement -> verify -> security chain
        self._chain(label_step, "coding", "qa")
        self._chain(label_step, "qa", "security")

        # research feeds implement (if present)
        self._chain(label_step, "research", "coding")

        # memory is the final step (persist outcome)
        if "memory" in label_step:
            memory_step = label_step["memory"]
            for step in steps:
                if step is not memory_step:
                    memory_step.dependencies.append(step.id)

        plan = Plan(steps=steps)
        for step in steps:
            # Register every step as a node, even one with no dependencies.
            # Otherwise a plan whose only step is `memory` produces an empty
            # graph, executes nothing, and still reports success.
            plan.graph.add_node(step.id)
            for dep in step.dependencies:
                plan.graph.add_edge(dep, step.id)
        plan.graph.validate()
        return plan

    # ------------------------------------------------------------------
    @staticmethod
    def _chain(label_step: dict[str, PlanStep], from_agent: str, to_agent: str) -> None:
        from_step = label_step.get(from_agent)
        to_step = label_step.get(to_agent)
        if from_step is not None and to_step is not None and from_step is not to_step:
            to_step.dependencies.append(from_step.id)