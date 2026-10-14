"""Phase 5 — Agent Intelligence tests.

Covers: decomposition, dependency ordering, parallel-safe tasks, agent
selection, failure recovery, result aggregation, bounded retries, and
circular dependency rejection.
"""
from __future__ import annotations

import pytest

from genesis.agents.base import Agent, AgentResult, AgentState, AgentTask
from genesis.agents.builtin import (
    CodingAgent,
    MemoryAgent,
    PlanningAgent,
    QAAgent,
    ResearchAgent,
    SecurityAgent,
    DeploymentAgent,
    register_builtin_agents,
)
from genesis.agents.registry import AgentRegistry
from genesis.coordinator.coordinator import AgentCoordinator, CoordinatorConfig
from genesis.coordinator.aggregator import aggregate
from genesis.exceptions import CircularDependencyError, RetryLimitExceeded
from genesis.planning.graph import DependencyGraph
from genesis.planning.planner import Planner, TaskDecomposer


# ------------------------------------------------------------------
# Task decomposition
# ------------------------------------------------------------------
def test_decomposer_splits_complex_task() -> None:
    decomposer = TaskDecomposer()
    subtasks = decomposer.decompose(
        "implement a function, add tests, and security review it"
    )
    labels = {s["label"] for s in subtasks}
    assert "implement" in labels
    assert "verify" in labels
    assert "security" in labels
    assert "memory" in labels


def test_decomposer_always_has_memory() -> None:
    decomposer = TaskDecomposer()
    subtasks = decomposer.decompose("do something vague")
    labels = {s["label"] for s in subtasks}
    assert "memory" in labels


# ------------------------------------------------------------------
# Planner + dependency ordering
# ------------------------------------------------------------------
def test_planner_assigns_agents() -> None:
    plan = Planner().plan("implement code and verify it")
    agents = {s.agent for s in plan.steps}
    assert "coding" in agents
    assert "qa" in agents


def test_planner_dependency_ordering() -> None:
    plan = Planner().plan("implement code and verify it")
    # memory must be last (depends on all others)
    memory_steps = [s for s in plan.steps if s.agent == "memory"]
    assert memory_steps
    memory_step = memory_steps[0]
    assert memory_step.dependencies
    # coding must precede qa
    qa_steps = [s for s in plan.steps if s.agent == "qa"]
    coding_steps = [s for s in plan.steps if s.agent == "coding"]
    assert qa_steps and coding_steps
    assert coding_steps[0].id in qa_steps[0].dependencies


def test_plan_graph_levels_are_parallel_safe() -> None:
    plan = Planner().plan("implement code and verify it")
    levels = plan.graph.levels()
    # No step appears twice; every step appears exactly once.
    seen = [sid for level in levels for sid in level]
    assert len(seen) == len(set(seen)) == len(plan.steps)


# ------------------------------------------------------------------
# Dependency graph
# ------------------------------------------------------------------
def test_graph_cycle_detection() -> None:
    graph = DependencyGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "c")
    graph.add_edge("c", "a")
    with pytest.raises(CircularDependencyError):
        graph.validate()


def test_graph_levels_ordering() -> None:
    graph = DependencyGraph()
    graph.add_edge("a", "c")
    graph.add_edge("b", "c")
    levels = graph.levels()
    assert levels[0] == ["a", "b"]  # parallel-safe
    assert levels[-1] == ["c"]


# ------------------------------------------------------------------
# Agent selection + execution
# ------------------------------------------------------------------
def test_agent_registry_selects_agents() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    assert registry.names() == [
        "coding", "deployment", "generic", "memory", "planning",
        "qa", "research", "security",
    ]
    assert registry.has("coding")
    assert registry.has("security")


def test_coding_agent_runs() -> None:
    agent = CodingAgent()
    result = agent.run(AgentTask(agent="coding", instruction="write a function"))
    assert result.ok
    assert result.status == AgentState.SUCCESS
    assert "implemented" in str(result.output)


def test_agent_cannot_execute_tool_directly() -> None:
    agent = CodingAgent()  # no tool gateway wired
    with pytest.raises(PermissionError):
        agent.request_tool("file.read", {"path": "/etc/passwd"})


# ------------------------------------------------------------------
# Coordinator: full plan execution
# ------------------------------------------------------------------
def test_coordinator_executes_plan() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    coordinator = AgentCoordinator(registry, Planner())
    summary = coordinator.run_task(task="implement code and verify it")
    assert isinstance(summary, str)
    assert summary


def test_coordinator_aggregates_results() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    coordinator = AgentCoordinator(registry, Planner())
    plan = Planner().plan("implement code and verify it")
    aggregated = coordinator.execute_plan(plan)
    assert aggregated.succeeded == len(plan.steps)
    assert aggregated.failed == 0
    assert aggregated.ok


def test_aggregate_collects_failures() -> None:
    results = [
        AgentResult(agent="a", status=AgentState.SUCCESS, output="ok"),
        AgentResult(agent="b", status=AgentState.FAILED, error="boom"),
    ]
    aggregated = aggregate(results)
    assert aggregated.failed == 1
    assert not aggregated.ok
    assert "boom" in aggregated.errors[0]


# ------------------------------------------------------------------
# Bounded retries + failure recovery
# ------------------------------------------------------------------
class FlakyAgent(Agent):
    name = "flaky"
    description = "Fails a fixed number of times then succeeds."

    def __init__(self, failures: int = 2) -> None:
        super().__init__()
        self.failures = failures
        self.calls = 0

    def run(self, task: AgentTask) -> AgentResult:
        self.calls += 1
        if self.calls <= self.failures:
            return AgentResult(
                agent=self.name, task_id=task.id, status=AgentState.FAILED,
                error="transient",
            )
        return AgentResult(
            agent=self.name, task_id=task.id, status=AgentState.SUCCESS,
            output="recovered",
        )


def test_bounded_retries_recover() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    registry.register("flaky", lambda: FlakyAgent(failures=2))
    plan = Planner().plan("implement code")
    # Replace the coding step with the flaky agent.
    for step in plan.steps:
        if step.agent == "coding":
            step.agent = "flaky"
    coordinator = AgentCoordinator(
        registry, Planner(), CoordinatorConfig(max_retries=4, retry_backoff_base=0.0)
    )
    aggregated = coordinator.execute_plan(plan)
    assert aggregated.ok
    assert aggregated.succeeded >= 1


def test_retry_limit_exceeded() -> None:
    class AlwaysFailAgent(Agent):
        name = "alwaysfail"

        def run(self, task: AgentTask) -> AgentResult:
            return AgentResult(
                agent=self.name, task_id=task.id, status=AgentState.FAILED,
                error="always",
            )

    registry = AgentRegistry()
    register_builtin_agents(registry)
    registry.register("alwaysfail", AlwaysFailAgent)
    plan = Planner().plan("implement code")
    # Re-route ALL steps through the failing agent to guarantee exhaustion.
    for step in plan.steps:
        step.agent = "alwaysfail"
    coordinator = AgentCoordinator(
        registry, Planner(), CoordinatorConfig(max_retries=2, retry_backoff_base=0.0)
    )
    with pytest.raises(RetryLimitExceeded):
        coordinator.execute_plan(plan)


def test_unknown_agent_raises() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    coordinator = AgentCoordinator(registry, Planner())
    plan = Planner().plan("implement code")
    for step in plan.steps:
        step.agent = "does-not-exist"
    with pytest.raises(RetryLimitExceeded):
        coordinator.execute_plan(plan)


# ------------------------------------------------------------------
# Circular dependency rejection through coordinator
# ------------------------------------------------------------------
def test_coordinator_rejects_circular_plan() -> None:
    registry = AgentRegistry()
    register_builtin_agents(registry)
    coordinator = AgentCoordinator(registry, Planner())
    graph = DependencyGraph()
    graph.add_edge("a", "b")
    graph.add_edge("b", "a")
    from genesis.planning.planner import Plan, PlanStep

    plan = Plan(
        steps=[
            PlanStep(id="a", agent="coding", instruction="a"),
            PlanStep(id="b", agent="qa", instruction="b"),
        ],
        graph=graph,
    )
    with pytest.raises(CircularDependencyError):
        coordinator.execute_plan(plan)


# ------------------------------------------------------------------
# Kernel integration
# ------------------------------------------------------------------
def test_kernel_uses_coordinator() -> None:
    from genesis.bootstrap import build
    from genesis.kernel.kernel import KernelRequest

    kernel = build()
    assert kernel.coordinator is not None
    resp = kernel.run(KernelRequest(task="implement a hello function and verify it"))
    assert resp.ok
    assert resp.result
    # The coordinator ran agents; memory was written.
    assert kernel.memory.list_scope(__import__("genesis").core.MemoryScope.TASK)