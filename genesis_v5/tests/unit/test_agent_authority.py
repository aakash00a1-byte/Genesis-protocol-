"""Agent tool mediation: agents ask, the Kernel decides.

These tests prove the boundary end to end: an agent with a bound gateway can
*request* a tool, the request travels the Kernel's authority gate, and a
denied request is surfaced (never silently executed). An agent with no gateway
cannot execute anything.
"""
from __future__ import annotations

from genesis.agents.base import AgentTask
from genesis.agents.builtin import CodingAgent, register_builtin_agents
from genesis.agents.registry import AgentRegistry
from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.coordinator.coordinator import AgentCoordinator
from genesis.kernel.kernel import KernelRequest
from genesis.planning.planner import Planner


def _kernel():
    return build(GenesisConfig(env=Env.TESTING, offline=True))


def test_agent_tool_request_goes_through_the_gate_and_is_granted() -> None:
    kernel = _kernel()
    result = kernel.agent_tool_request(
        "file.list",
        {"path": "/workspace"},
        actor="agent:coding",
        role="coder",  # coder holds file.list
    )
    assert result.status.value == "success"
    assert result.ok


def test_agent_tool_request_is_denied_for_insufficient_role() -> None:
    kernel = _kernel()
    # researcher does not hold file.write -> the gate denies it.
    result = kernel.agent_tool_request(
        "file.write",
        {"path": "/workspace/should_not_exist.txt", "content": "x"},
        actor="agent:research",
        role="researcher",
    )
    assert not result.ok
    assert result.status.value == "denied"
    from pathlib import Path

    assert not Path("/workspace/should_not_exist.txt").exists()


def test_agent_tool_request_respects_the_risk_ceiling() -> None:
    kernel = _kernel()
    # terminal.run is HIGH; the default agent ceiling is MEDIUM, so even an
    # admin agent cannot request it through this path without raising the bar.
    result = kernel.agent_tool_request(
        "terminal.run",
        {"command": "echo hi"},
        actor="agent:op",
        role="admin",
    )
    assert not result.ok
    assert result.status.value == "denied"


def test_agent_without_gateway_cannot_execute() -> None:
    agent = CodingAgent()  # no gateway bound
    task = AgentTask(
        agent="coding",
        instruction="list files",
        metadata={"tool": "file.list", "args": {"path": "/workspace"}},
    )
    result = agent.run(task)
    assert result.ok
    # The agent reports that it had no gateway; it did not execute anything.
    assert result.metadata["tool"]["executed"] is False
    assert result.metadata["tool"]["status"] == "no_gateway"


def test_agent_with_bound_gateway_routes_through_kernel() -> None:
    kernel = _kernel()
    agent = CodingAgent()
    agent.bind_tool_request(
        lambda name, args: kernel.agent_tool_request(
            name, args, "agent:coding", "coder"
        )
    )
    task = AgentTask(
        agent="coding",
        instruction="list files",
        metadata={"tool": "file.list", "args": {"path": "/workspace"}},
    )
    result = agent.run(task)
    assert result.ok
    assert result.metadata["tool"]["executed"] is True
    assert result.metadata["tool"]["status"] == "success"


def test_coordinator_binds_gateway_to_agents() -> None:
    kernel = _kernel()
    registry = AgentRegistry()
    register_builtin_agents(registry)
    coordinator = AgentCoordinator(
        registry,
        Planner(),
        tool_request=kernel.agent_tool_request,
    )
    summary = coordinator.run_task(task="implement and verify a helper")
    assert isinstance(summary, str)
    assert summary


def test_kernel_health_reports_subsystems() -> None:
    kernel = _kernel()
    health = kernel.health()
    assert health["health"]["status"] in {"ok", "degraded"}
    assert {c["name"] for c in health["health"]["checks"]} >= {
        "memory", "tools", "audit", "coordinator", "qa",
    }
    assert "metrics" in health


def test_kernel_run_records_risk_and_metrics() -> None:
    kernel = _kernel()
    resp = kernel.run(KernelRequest(task="summarize the build status", actor="u"))
    assert resp.risk is not None
    assert resp.risk["level"] == "low"
    assert kernel.metrics.counter("kernel.risk.assessments") >= 1
    assert kernel.metrics.counter("kernel.runs") >= 1


def test_kernel_run_flags_a_high_risk_task() -> None:
    kernel = _kernel()
    resp = kernel.run(
        KernelRequest(task="rm -rf / in production and bypass the gate", actor="u")
    )
    assert resp.risk["level"] in {"high", "critical"}
    # No alert provider is wired, so the undelivered alert is recorded, not hidden.
    failures = kernel.transparency.failures.failures()
    assert any(f.component == "kernel.risk_alert" for f in failures)
