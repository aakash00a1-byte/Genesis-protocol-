"""Genesis V6 — multi-agent integration.

End-to-end paths across the real wiring (no mocks of the gate itself):

  user -> Kernel -> planner -> coordinator -> agent -> authority gate ->
  tool/sandbox -> result -> reflection -> QA -> memory -> audit.

Covers: multi-agent delegation, role-based denial, risk-ceiling enforcement,
tool failure, tool timeout, bounded retries, deterministic parallel ordering,
QA rejection of incorrect output, task-context propagation, and memory/secret
isolation between actors.
"""
from __future__ import annotations

import time

import pytest
from genesis.agents.base import Agent, AgentResult, AgentState, AgentTask
from genesis.agents.builtin import register_builtin_agents
from genesis.agents.registry import AgentRegistry
from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.coordinator.coordinator import AgentCoordinator, CoordinatorConfig
from genesis.core import MemoryScope, RiskLevel
from genesis.exceptions import RetryLimitExceeded
from genesis.kernel.kernel import KernelRequest
from genesis.planning.planner import Planner
from genesis.security.permissions import Permission
from genesis.tools.registry import ToolCategory, ToolSpec


def _kernel(**kwargs):
    return build(GenesisConfig(env=Env.TESTING, offline=True, **kwargs))


def _register_probe_tool(kernel, name, handler, *, risk=RiskLevel.LOW, timeout=30.0):
    """Register a low-risk probe tool on the real registry/gateway."""
    spec = ToolSpec(
        name=name,
        category=ToolCategory.FILES,
        description="integration probe",
        schema={"title": name, "properties": {}, "required": []},
        permission=Permission.FILE_LIST,
        risk_level=risk,
        timeout_seconds=timeout,
    )
    kernel.tools.register(spec, handler)


# ------------------------------------------------------------------
# 1. Multi-agent delegation end to end
# ------------------------------------------------------------------
def test_kernel_delegates_to_multiple_agents() -> None:
    kernel = _kernel()
    resp = kernel.run(
        KernelRequest(task="implement a cache and verify it", actor="u", role="coder")
    )
    assert resp.ok, resp.errors
    assert resp.result
    # The coordinator planned several agents; the aggregate names them.
    plan = kernel.coordinator.planner.plan("implement a cache and verify it")
    assert {"coding", "qa", "memory"} <= {s.agent for s in plan.steps}
    assert resp.qa is not None and resp.qa["passed"] is True


def test_agent_receives_the_originating_task_context() -> None:
    """Regression: agents used to receive an empty task context."""
    seen: dict[str, str] = {}

    class Spy(Agent):
        name = "spy"
        description = "captures context"

        def run(self, task: AgentTask) -> AgentResult:
            seen[task.agent] = task.context.get("task", "")
            return AgentResult(agent=self.name, task_id=task.id, output="ok")

    registry = AgentRegistry()
    register_builtin_agents(registry)
    # Route every agent label the planner may pick through the spy.
    for name in ("coding", "qa", "memory", "security", "planning", "research", "deployment"):
        registry.register(name, lambda: Spy())
    coordinator = AgentCoordinator(registry, Planner())
    # run_task is the real entry point (the Kernel uses it); it seeds the task
    # context before planning.
    coordinator.run_task(task="implement a cache and verify it")
    assert seen, "spy must have run"
    assert all(v == "implement a cache and verify it" for v in seen.values())


# ------------------------------------------------------------------
# 2. Role-based denial through the agent path
# ------------------------------------------------------------------
def test_researcher_cannot_write_files() -> None:
    kernel = _kernel()
    result = kernel.agent_tool_request(
        "file.write",
        {"path": "/workspace/denied.txt", "content": "x"},
        "agent:research",
        "researcher",
    )
    assert not result.ok
    assert result.status.value == "denied"
    from pathlib import Path

    assert not Path("/workspace/denied.txt").exists()


def test_coder_can_list_but_not_docker() -> None:
    kernel = _kernel()
    ok = kernel.agent_tool_request("file.list", {"path": "."}, "a", "coder")
    assert ok.ok
    denied = kernel.agent_tool_request("docker.exec", {"command": "ls"}, "a", "coder")
    assert not denied.ok


# ------------------------------------------------------------------
# 3. Risk-ceiling enforcement on the agent path
# ------------------------------------------------------------------
def test_agent_risk_ceiling_blocks_high_risk_tool() -> None:
    kernel = _kernel()
    # terminal.run is HIGH; the agent path ceilings at MEDIUM even for admin.
    result = kernel.agent_tool_request(
        "terminal.run", {"command": "echo hi"}, "agent:op", "admin"
    )
    assert not result.ok
    assert result.status.value == "denied"


def test_agent_risk_ceiling_is_raisable_explicitly() -> None:
    kernel = _kernel()
    # Raising the ceiling is an explicit, auditable decision by the caller.
    result = kernel.agent_tool_request(
        "terminal.run", {"command": "echo hi"}, "agent:op", "admin",
        max_risk=RiskLevel.HIGH,
    )
    assert result.ok


# ------------------------------------------------------------------
# 4. Tool failure is surfaced, never hidden
# ------------------------------------------------------------------
def test_tool_failure_is_surfaced_to_the_agent() -> None:
    kernel = _kernel()

    def boom(context, args):
        raise RuntimeError("handler exploded")

    _register_probe_tool(kernel, "probe.fail", boom)
    result = kernel.agent_tool_request("probe.fail", {}, "a", "coder")
    assert not result.ok
    assert result.status.value == "failure"
    assert "exploded" in result.error
    # Audited as a failure, not silently dropped.
    assert any(
        e.get("event_type") == "tool_failure" for e in kernel.audit.events()
    )


def test_agent_records_a_failed_tool_request() -> None:
    kernel = _kernel()
    _register_probe_tool(kernel, "probe.fail", lambda c, a: (_ for _ in ()).throw(RuntimeError("nope")))
    from genesis.agents.builtin import CodingAgent

    agent = CodingAgent()
    agent.bind_tool_request(lambda n, a: kernel.agent_tool_request(n, a, "a", "coder"))
    task = AgentTask(
        agent="coding", instruction="do it",
        metadata={"tool": "probe.fail", "args": {}},
    )
    result = agent.run(task)
    assert result.ok  # the agent ran; the tool failed
    assert result.metadata["tool"]["executed"] is False
    assert result.metadata["tool"]["status"] == "failure"


# ------------------------------------------------------------------
# 5. Tool timeout is bounded and surfaced
# ------------------------------------------------------------------
def test_tool_timeout_is_surfaced() -> None:
    kernel = _kernel()

    def slow(context, args):
        time.sleep(0.5)
        return "too late"

    _register_probe_tool(kernel, "probe.slow", slow, timeout=0.05)
    result = kernel.agent_tool_request("probe.slow", {}, "a", "coder")
    assert not result.ok
    assert result.status.value == "timeout"


# ------------------------------------------------------------------
# 6. Bounded retries
# ------------------------------------------------------------------
def test_retry_limit_is_bounded_and_raises() -> None:
    class AlwaysFail(Agent):
        name = "alwaysfail"
        description = "always fails"

        def run(self, task: AgentTask) -> AgentResult:
            return AgentResult(
                agent=self.name, task_id=task.id, status=AgentState.FAILED, error="no"
            )

    registry = AgentRegistry()
    register_builtin_agents(registry)
    registry.register("alwaysfail", AlwaysFail)
    coordinator = AgentCoordinator(
        registry, Planner(), CoordinatorConfig(max_retries=2, retry_backoff_base=0.0)
    )
    plan = Planner().plan("implement code")
    for step in plan.steps:
        step.agent = "alwaysfail"
    with pytest.raises(RetryLimitExceeded):
        coordinator.execute_plan(plan)


def test_retry_recovers_within_limit() -> None:
    class Flaky(Agent):
        name = "flaky"
        description = "fails once"

        def __init__(self):
            super().__init__()
            self.calls = 0

        def run(self, task: AgentTask) -> AgentResult:
            self.calls += 1
            if self.calls < 2:
                return AgentResult(
                    agent=self.name, task_id=task.id, status=AgentState.FAILED, error="x"
                )
            return AgentResult(agent=self.name, task_id=task.id, output="recovered")

    registry = AgentRegistry()
    register_builtin_agents(registry)
    registry.register("flaky", Flaky)
    coordinator = AgentCoordinator(
        registry, Planner(), CoordinatorConfig(max_retries=3, retry_backoff_base=0.0)
    )
    plan = Planner().plan("implement code")
    for step in plan.steps:
        step.agent = "flaky"
    aggregated = coordinator.execute_plan(plan)
    assert aggregated.ok


# ------------------------------------------------------------------
# 7. QA rejection of incorrect output
# ------------------------------------------------------------------
def test_qa_rejects_output_with_failure_markers() -> None:
    kernel = _kernel()
    # The built-in agents append a failure marker when asked to inject one.
    resp = kernel.run(
        KernelRequest(
            task="implement INJECT-FAILURE and verify it", actor="u", role="coder"
        )
    )
    assert resp.qa is not None
    assert resp.qa["passed"] is False
    assert not resp.ok
    assert any("qa_failed" in e for e in resp.errors)
    # The rejection is recorded, not hidden.
    failures = kernel.transparency.failures.failures()
    assert any(f.component == "kernel.qa" for f in failures)


def test_qa_rejects_empty_result() -> None:
    kernel = _kernel()
    outcome = kernel.qa.verify(task="t", result="")
    assert not outcome.passed
    assert "empty result" in outcome.issues


# ------------------------------------------------------------------
# 8. Deterministic parallel ordering
# ------------------------------------------------------------------
def test_parallel_level_output_order_is_deterministic() -> None:
    orders = set()
    for _ in range(30):
        registry = AgentRegistry()
        register_builtin_agents(registry)
        coordinator = AgentCoordinator(
            registry, Planner(), CoordinatorConfig(max_parallel=4)
        )
        plan = Planner().plan("research the topic and deploy the package")
        aggregated = coordinator.execute_plan(plan)
        orders.add(tuple(aggregated.outputs))
    assert len(orders) == 1, f"non-deterministic ordering: {len(orders)} variants"


def test_parallel_errors_surface_deterministically() -> None:
    class Boom(Agent):
        name = "boom"
        description = "raises"

        def run(self, task: AgentTask) -> AgentResult:
            raise RuntimeError(f"boom:{task.agent}")

    registry = AgentRegistry()
    register_builtin_agents(registry)
    registry.register("boom", Boom)
    coordinator = AgentCoordinator(
        registry, Planner(), CoordinatorConfig(max_retries=1, retry_backoff_base=0.0)
    )
    plan = Planner().plan("research the topic and deploy the package")
    for step in plan.steps:
        step.agent = "boom"
    messages = set()
    for _ in range(10):
        try:
            coordinator.execute_plan(plan)
        except RetryLimitExceeded as exc:
            messages.add(str(exc))
    assert len(messages) == 1, f"non-deterministic error: {messages}"


# ------------------------------------------------------------------
# 9. Memory scope + secret isolation
# ------------------------------------------------------------------
def test_memory_scopes_are_isolated() -> None:
    kernel = _kernel()
    kernel.memory_write(
        MemoryScope.TASK, "k", {"v": "task-only"}, actor="a"
    )
    task_hits = kernel.memory_search("task-only", scopes=[MemoryScope.TASK], actor="a")
    project_hits = kernel.memory_search(
        "task-only", scopes=[MemoryScope.PROJECT], actor="a"
    )
    assert task_hits
    assert not project_hits


def test_secrets_are_redacted_before_memory_persistence() -> None:
    kernel = _kernel()
    secret = "sk-" + "a" * 32
    kernel.memory_write(
        MemoryScope.PROJECT, "note", {"token": secret}, actor="a"
    )
    entry = kernel.memory.read(MemoryScope.PROJECT, "note")
    assert entry is not None
    assert secret not in str(entry.value)


def test_credential_path_is_blocked_by_the_sandbox() -> None:
    kernel = _kernel()
    result = kernel.agent_tool_request(
        "file.read", {"path": "/etc/passwd"}, "a", "coder"
    )
    assert not result.ok
    assert result.status.value in ("sandbox_violation", "denied")


def test_agent_tool_request_is_audited_with_the_real_actor() -> None:
    kernel = _kernel()
    kernel.agent_tool_request("file.list", {"path": "."}, "agent:coding", "coder")
    events = [e for e in kernel.audit.events() if e.get("event_type") == "tool_exec"]
    assert events
    assert events[-1]["actor"] == "agent:coding"
