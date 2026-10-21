"""Regressions for the hardening pass.

Each test pins a defect found by probing the real gate / gateway:

* a forbidden tool (docker.exec) is refused by the *gate* even for an admin
  agent, not just by the autonomy loop's pre-check;
* an oversized chat message is rejected before parsing;
* the gateway refuses an unknown channel and an empty allow-list (deny by
  default) — already true, kept here as a tripwire.
"""
from __future__ import annotations

import tempfile

from genesis.bootstrap import build, build_chat_gateway
from genesis.config.settings import (
    AutonomyConfig,
    Env,
    GenesisConfig,
    IntegrationConfig,
)
from genesis.core import RiskLevel
from genesis.tools.builtin import build_default_registry
from genesis.tools.gateway import ToolGateway, ToolRequest


def _kernel(*, autonomy_enabled: bool):
    cfg = GenesisConfig(
        env=Env.TESTING,
        offline=True,
        autonomy=AutonomyConfig(
            enabled=autonomy_enabled, checkpoint_dir=tempfile.mkdtemp()
        ),
        integration=IntegrationConfig(
            enabled=True, allowed_channels=["C1"], default_role="none"
        ),
    )
    return build(cfg), cfg


# -- forbidden tool is enforced at the gate, not only by the loop ----------
def test_forbidden_tool_denied_for_admin_role() -> None:
    gateway = ToolGateway(build_default_registry())
    gateway.forbid_tools({"docker.exec", "terminal.run"})
    for tool in ("docker.exec", "terminal.run"):
        result = gateway.execute(
            ToolRequest(tool=tool, args={}, actor="anyone", role="admin"),
            max_risk=RiskLevel.CRITICAL,
        )
        assert result.status.value == "denied", tool
        assert result.audit_event.details.get("reason") == "forbidden_tool"


def test_autonomy_enabled_forbids_dangerous_tools_via_kernel() -> None:
    kernel, _ = _kernel(autonomy_enabled=True)
    # An admin agent asks for a CRITICAL tool. With autonomy enabled the gate
    # refuses it outright, so a role can never reach it on the agent path.
    result = kernel.agent_tool_request(
        "docker.exec", {}, actor="agent", role="admin", max_risk=RiskLevel.CRITICAL,
    )
    assert result.status.value == "denied"


def test_autonomy_disabled_keeps_default_gate_behaviour() -> None:
    kernel, _ = _kernel(autonomy_enabled=False)
    # Without autonomy the forbidden list is not installed; an admin role is
    # still bound by the normal risk ceiling (HIGH tool under a LOW ceiling is
    # denied), which is the pre-existing, tested behaviour.
    result = kernel.agent_tool_request(
        "terminal.run", {}, actor="agent", role="admin"
    )
    assert result.status.value == "denied"


# -- chat message bound -----------------------------------------------------
def test_oversized_chat_message_is_rejected() -> None:
    kernel, cfg = _kernel(autonomy_enabled=True)
    gw = build_chat_gateway(kernel, config=cfg)
    reply = gw.handle(channel="C1", sender="u", text="/task " + "x" * 5000)
    assert reply.ok is False
    assert reply.details.get("reason") == "message_too_long"


def test_unknown_channel_is_refused() -> None:
    kernel, cfg = _kernel(autonomy_enabled=True)
    gw = build_chat_gateway(kernel, config=cfg)
    reply = gw.handle(channel="NOT-ALLOWED", sender="u", text="/help")
    assert reply.ok is False
    assert reply.details.get("reason") == "channel_not_allowed"
