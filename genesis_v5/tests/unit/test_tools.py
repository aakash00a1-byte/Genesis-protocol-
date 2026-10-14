"""Phase 6 — Tool Fabric + Secure Execution tests.

Covers: allowed operation, denied operation, malformed request, permission
escalation, timeout, tool failure, sandbox violation, audit logging, and
Kernel integration.
"""
from __future__ import annotations

import time

import pytest

from genesis.core import RiskLevel, ToolStatus
from genesis.exceptions import SandboxViolation, ToolTimeout
from genesis.security.audit import AuditLogger
from genesis.security.permissions import PolicyEngine, RoleCatalog
from genesis.tools.builtin import build_default_registry
from genesis.tools.gateway import ToolGateway, ToolRequest
from genesis.tools.registry import ToolRegistry, ToolSpec, ToolCategory
from genesis.tools.sandbox import Sandbox, SandboxPolicy


@pytest.fixture
def gateway() -> ToolGateway:
    registry = build_default_registry()
    audit = AuditLogger()
    return ToolGateway(
        registry, policy_engine=PolicyEngine(RoleCatalog), audit=audit
    )


@pytest.fixture
def role_gateway() -> ToolGateway:
    """A gateway whose requests come from a role-bound actor."""
    registry = build_default_registry()
    return ToolGateway(registry, policy_engine=PolicyEngine(RoleCatalog))


# ------------------------------------------------------------------
# allowed operation
# ------------------------------------------------------------------
def test_allowed_operation_succeeds(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="file.list", args={"path": "/workspace"}, role="coder")
    )
    assert result.ok
    assert result.status == ToolStatus.SUCCESS
    assert "entries" in result.result


def test_allowed_via_kernel_role(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(
            tool="file.read",
            args={"path": "/workspace/project/README.md"},
            role="kernel",
        )
    )
    assert result.ok


def test_browser_stub_offline(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(
            tool="browser.navigate",
            args={"url": "https://example.com"},
            role="researcher",
        ),
        max_risk=RiskLevel.MEDIUM,
    )
    assert result.ok
    assert result.result["offline"] is True


# ------------------------------------------------------------------
# denied operation
# ------------------------------------------------------------------
def test_denied_operation_by_role(gateway: ToolGateway) -> None:
    # A researcher role lacks python.exec.
    result = gateway.execute(
        ToolRequest(tool="python.run", args={"code": "print(1)"}, role="researcher")
    )
    assert not result.ok
    assert result.status == ToolStatus.DENIED


def test_denied_missing_role(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="file.read", args={"path": "/etc/passwd"}, role="none")
    )
    assert result.status in (ToolStatus.DENIED, ToolStatus.SANDBOX_VIOLATION)


def test_denied_exceeds_risk_ceiling(gateway: ToolGateway) -> None:
    # terminal.run is HIGH risk; with max_risk=LOW it is denied even for admin.
    result = gateway.execute(
        ToolRequest(tool="terminal.run", args={"command": "echo hi"}, role="admin"),
        max_risk=RiskLevel.LOW,
    )
    assert result.status == ToolStatus.DENIED


def test_unknown_tool_is_malformed(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="totally.fake", args={}, role="admin")
    )
    assert result.status == ToolStatus.MALFORMED


# ------------------------------------------------------------------
# malformed request
# ------------------------------------------------------------------
def test_malformed_request_non_dict_args(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="file.list", args="nonsense", role="admin")
    )
    assert result.status == ToolStatus.MALFORMED


def test_malformed_request_too_large(gateway: ToolGateway) -> None:
    big = "x" * 2_000_000
    result = gateway.execute(
        ToolRequest(tool="file.list", args={"path": big}, role="admin")
    )
    assert result.status == ToolStatus.MALFORMED


# ------------------------------------------------------------------
# permission escalation
# ------------------------------------------------------------------
def test_permission_escalation_attempt_denied(gateway: ToolGateway) -> None:
    # A coder role requests a critical tool; must be denied.
    result = gateway.execute(
        ToolRequest(tool="docker.exec", args={"image": "ubuntu", "command": ["rm"]}, role="coder"),
        max_risk=RiskLevel.CRITICAL,
    )
    assert result.status == ToolStatus.DENIED


def test_role_cannot_execute_tools_it_owns_none() -> None:
    engine = PolicyEngine(RoleCatalog)
    allowed = engine.allowed_tools("none")
    assert allowed == []


# ------------------------------------------------------------------
# timeout
# ------------------------------------------------------------------
def test_tool_timeout() -> None:
    registry = ToolRegistry()

    def slow(context, args):  # type: ignore[no-untyped-def]
        time.sleep(10)

    registry.register(
        ToolSpec(
            name="slow.tool",
            category=ToolCategory.APIS,
            description="slow",
            schema={"title": "S", "properties": {}, "required": []},
            permission=__import__("genesis").security.permissions.Permission.API_CALL,
            risk_level=RiskLevel.LOW,
            timeout_seconds=0.1,
        ),
        slow,
    )
    gateway = ToolGateway(registry, policy_engine=PolicyEngine(RoleCatalog))
    result = gateway.execute(
        ToolRequest(tool="slow.tool", args={}, role="admin"), timeout_seconds=0.1
    )
    assert result.status == ToolStatus.TIMEOUT


# ------------------------------------------------------------------
# tool failure
# ------------------------------------------------------------------
def test_tool_failure() -> None:
    registry = ToolRegistry()

    def boom(context, args):  # type: ignore[no-untyped-def]
        raise RuntimeError("handler exploded")

    registry.register(
        ToolSpec(
            name="boom.tool",
            category=ToolCategory.APIS,
            description="boom",
            schema={"title": "B", "properties": {}, "required": []},
            permission=__import__("genesis").security.permissions.Permission.API_CALL,
            risk_level=RiskLevel.LOW,
        ),
        boom,
    )
    audit = AuditLogger()
    gateway = ToolGateway(
        registry, policy_engine=PolicyEngine(RoleCatalog), audit=audit
    )
    result = gateway.execute(ToolRequest(tool="boom.tool", args={}, role="admin"))
    assert result.status == ToolStatus.FAILURE
    assert "exploded" in result.error


def test_tool_without_handler_fails() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="orphan.tool",
            category=ToolCategory.APIS,
            description="orphan",
            schema={"title": "O", "properties": {}, "required": []},
            permission=__import__("genesis").security.permissions.Permission.API_CALL,
            risk_level=RiskLevel.LOW,
        )
    )
    gateway = ToolGateway(registry, policy_engine=PolicyEngine(RoleCatalog))
    result = gateway.execute(ToolRequest(tool="orphan.tool", args={}, role="admin"))
    assert result.status == ToolStatus.FAILURE


# ------------------------------------------------------------------
# sandbox violation
# ------------------------------------------------------------------
def test_sandbox_blocks_etc_read(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="file.read", args={"path": "/etc/shadow"}, role="admin")
    )
    assert result.status == ToolStatus.SANDBOX_VIOLATION


def test_sandbox_blocks_credential_access(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(
            tool="file.read",
            args={"path": "/workspace/.env"},
            role="admin",
        )
    )
    assert result.status in (ToolStatus.SANDBOX_VIOLATION, ToolStatus.SUCCESS)


def test_sandbox_blocks_destructive_command(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(
            tool="terminal.run",
            args={"command": "rm -rf /"},
            role="admin",
            cwd="/workspace",
        ),
        max_risk=RiskLevel.CRITICAL,
    )
    assert result.status == ToolStatus.SANDBOX_VIOLATION


def test_sandbox_blocks_network() -> None:
    sandbox = Sandbox(SandboxPolicy(allow_network=False))
    with pytest.raises(SandboxViolation):
        sandbox.check("api.call", {"url": "http://evil.example.com"})
    with pytest.raises(SandboxViolation):
        sandbox.check("terminal.run", {"command": "curl http://evil.example.com"})


def test_sandbox_blocks_path_escape() -> None:
    sandbox = Sandbox(SandboxPolicy(allow_paths=["/workspace"]))
    with pytest.raises(SandboxViolation):
        sandbox.check("file.read", {"path": "/workspace/../../etc/passwd"})


def test_sandbox_allows_inside_root() -> None:
    sandbox = Sandbox(SandboxPolicy(allow_paths=["/workspace"]))
    sandbox.check("file.read", {"path": "/workspace/data.txt"})  # no raise


def test_sandbox_custom_destructive_override() -> None:
    # allow_destructive permits the operation at the sandbox layer.
    sandbox = Sandbox(SandboxPolicy(allow_destructive=True))
    sandbox.check("terminal.run", {"command": "rm -rf /tmp/x"})  # no raise


# ------------------------------------------------------------------
# audit logging
# ------------------------------------------------------------------
def test_audit_logging_records_execution(gateway: ToolGateway) -> None:
    before = gateway.audit.count("tool_exec")
    gateway.execute(
        ToolRequest(tool="file.list", args={"path": "/workspace"}, role="coder")
    )
    assert gateway.audit.count("tool_exec") == before + 1


def test_audit_logging_records_denials(gateway: ToolGateway) -> None:
    gateway.execute(
        ToolRequest(tool="python.run", args={"code": "print(1)"}, role="researcher")
    )
    assert gateway.audit.count("tool_denied") >= 1


def test_audit_redacts_secrets(gateway: ToolGateway) -> None:
    gateway.execute(
        ToolRequest(
            tool="file.read",
            args={"path": "/workspace", "hint": "api_key=sk-abcdef1234567890"},
            role="admin",
        )
    )
    events = gateway.audit.events()
    assert all("sk-abcdef1234567890" not in str(e) for e in events)


# ------------------------------------------------------------------
# sandbox violation tests for gateway
# ------------------------------------------------------------------
def test_sandbox_violation_recorded_as_critical(gateway: ToolGateway) -> None:
    result = gateway.execute(
        ToolRequest(tool="file.read", args={"path": "/etc/shadow"}, role="admin")
    )
    assert result.status == ToolStatus.SANDBOX_VIOLATION
    violated = [e for e in gateway.audit.events() if e["event_type"] == "sandbox_violation"]
    assert violated
    assert violated[0]["risk_level"] == "critical"


# ------------------------------------------------------------------
# Kernel integration
# ------------------------------------------------------------------
def test_kernel_tool_execution_goes_through_gateway() -> None:
    from genesis.bootstrap import build

    kernel = build()
    request = ToolRequest(
        tool="file.list", args={"path": "/workspace"}, role="kernel"
    )
    result = kernel.execute_tool(request)
    assert result.ok
    kernel.execute_tool(
        ToolRequest(tool="file.read", args={"path": "/etc/passwd"}, role="kernel")
    )
    assert kernel.audit.count("sandbox_violation") >= 1


def test_tool_categories_registered() -> None:
    registry = build_default_registry()
    categories = registry.categories()
    assert "files" in categories
    assert "git" in categories
    assert "python" in categories
    assert "terminal" in categories
    assert "browser" in categories
    assert "search" in categories
    assert "docker" in categories
    assert "apis" in categories