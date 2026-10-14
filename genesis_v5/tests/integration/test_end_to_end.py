"""Genesis V5 — End-to-End offline integration scenario.

Exercises the complete pipeline without internet, API keys, paid services,
large model downloads, or production deployment:

    User -> Genesis API (Kernel.run) -> Memory Retrieval -> Task
    Classification -> Planner -> Model Router -> Agent Coordinator ->
    Tool Permission -> Sandbox -> Agent Execution -> Reflection ->
    Independent QA -> Memory Write -> Final Result -> Audit Event
"""
from __future__ import annotations

import os

import pytest

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.core import MemoryScope
from genesis.exceptions import PermissionDenied, SandboxViolation
from genesis.kernel.kernel import KernelRequest
from genesis.runtime.lifecycle import ApplicationRuntime
from genesis.security.core import SecurityCore
from genesis.security.permissions import Permission
from genesis.tools.gateway import ToolRequest


def test_full_offline_pipeline() -> None:
    cfg = GenesisConfig(
        env=Env.TESTING,
        offline=True,
    )
    kernel = build(cfg)

    response = kernel.run(
        KernelRequest(
            task="Summarize the project roadmap in 30 words",
            actor="e2e-user",
            role="admin",
            scope=MemoryScope.TASK,
        )
    )

    assert response.ok, response.errors
    assert response.result
    assert response.memory is not None
    assert response.audit_ids, "audit trail must exist"
    assert response.reflection is not None, "reflection stage must run"
    assert response.qa is not None, "independent QA must run"
    assert response.qa["passed"] is True


def test_pipeline_writes_verifiable_memory() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    kernel.run(
        KernelRequest(
            task="Write a short design note for the caching layer",
            actor="e2e-user",
            scope=MemoryScope.PROJECT,
        )
    )
    hits = kernel.memory_search(
        "caching design", scopes=[MemoryScope.PROJECT], actor="e2e-user"
    )
    assert hits, "memory must contain the design note"


def test_tool_permission_and_sandbox_deny_by_default() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)

    # Unauthorized tool request: role "qa" cannot write files.
    denied = kernel.execute_tool(
        ToolRequest(
            tool="file.write",
            args={"path": "/workspace/evil.txt", "content": "x"},
            actor="e2e-role",  # role comes from policy, see request below
            role="qa",
        )
    )
    assert not denied.ok
    assert denied.status.value in ("denied", "permission_denied", "malformed")

    # Sandbox boundary: reading outside the root is blocked.
    blocked = kernel.execute_tool(
        ToolRequest(
            tool="file.read",
            args={"path": "/etc/passwd"},
            actor="e2e-user",
            role="admin",
            cwd="/workspace",
        )
    )
    assert not blocked.ok
    assert "sandbox" in blocked.error.lower() or blocked.status.value == "denied"


def test_allowed_tool_execution_flows_through_gate() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    result = kernel.execute_tool(
        ToolRequest(
            tool="file.list",
            args={"path": "."},
            actor="e2e-user",
            role="admin",
            cwd="/workspace",
        )
    )
    assert result.ok
    assert "entries" in result.result


def test_audit_trail_exists_for_tool_and_kernel() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    kernel.execute_tool(
        ToolRequest(tool="file.list", args={}, actor="audit-user", role="admin")
    )
    event_types = [e.get("event_type") for e in kernel.audit.events()]
    assert "tool_exec" in event_types


def test_invalid_tool_rejected_as_malformed() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    result = kernel.execute_tool(
        ToolRequest(tool="does.not.exist", args={}, actor="user", role="admin")
    )
    assert not result.ok
    assert result.status.value == "malformed"


def test_security_core_blocks_privilege_escalation() -> None:
    from genesis.security.core import Principal

    core = SecurityCore()

    # Authentication boundary: unknown roles collapse to zero-trust.
    principal = core.authenticate("normal-user", "qa")
    assert principal.role == "qa"

    # qa can read memory but not write it.
    assert core.authorize(principal, Permission.MEMORY_READ)
    with pytest.raises(PermissionDenied):
        core.authorize(principal, Permission.MEMORY_WRITE)

    # Unknown roles get no implicit authority.
    intruder = core.authenticate("mystery-agent", "rootSuperuser")
    assert intruder.role == "none"
    with pytest.raises(PermissionDenied):
        core.authorize(intruder, Permission.TERMINAL_EXEC)


def test_runtime_ready_and_graceful_shutdown() -> None:
    runtime = ApplicationRuntime(max_workers=2)
    runtime.on_shutdown(lambda: None)
    runtime.start()
    assert runtime.health.ready().status == "ok"
    runtime.shutdown()
    assert runtime.status()["started"] is False


def test_production_config_has_no_credentials() -> None:
    cfg = GenesisConfig(env=Env.PRODUCTION, offline=True)
    blob = f"{cfg}".lower()
    assert "api_key" not in blob or "mock" in blob
    assert cfg.is_production
    # No provider is forced on: adapters stay disabled without env credentials.
    assert cfg.router.default_provider == "mock"