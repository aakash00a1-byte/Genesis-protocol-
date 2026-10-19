"""Bounded standing auto-grant: a pre-authorised, low-risk, read-only path.

The gate is never removed. These tests prove the narrow grant only fires when
actor AND permission AND the LOW risk ceiling all agree, and that it can never
reach a write or a HIGH/CRITICAL tool.
"""
from __future__ import annotations

from pathlib import Path

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig, SecurityConfig
from genesis.tools.gateway import ToolRequest


def _kernel(**security):
    cfg = GenesisConfig(
        env=Env.TESTING,
        offline=True,
        security=SecurityConfig(**security),
    )
    return build(cfg)


def _read(path: str, actor: str = "autonomy"):
    return ToolRequest(tool="file.read", args={"path": path}, actor=actor, role="none")


def test_default_has_no_standing_grant(tmp_path) -> None:
    # Empty allow-list => the gate is fully enforced; a read is denied.
    f = tmp_path / "x.txt"
    f.write_text("hi")
    kernel = _kernel()
    assert kernel.execute_tool(_read(str(f))).status.value == "denied"


def test_grant_allows_listed_low_risk_read(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    kernel = _kernel(auto_grant_permissions=["file.read"])
    result = kernel.execute_tool(_read(str(f)))
    assert result.status.value != "denied", result.error


def test_grant_does_not_cover_a_write() -> None:
    # file.write is not in the allow-list, so the write is still gated.
    kernel = _kernel(auto_grant_permissions=["file.read"])
    result = kernel.execute_tool(
        ToolRequest(
            tool="file.write",
            args={"path": "/workspace/genesis_grant_test.txt", "content": "y"},
            actor="autonomy",
            role="none",
        )
    )
    assert result.status.value == "denied"


def test_grant_is_scoped_to_the_named_actor(tmp_path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hi")
    kernel = _kernel(auto_grant_permissions=["file.read"])
    assert kernel.execute_tool(_read(str(f), actor="someone-else")).status.value == "denied"


def test_grant_never_escalates_above_low_risk() -> None:
    # file.write is MEDIUM risk: even when its permission is listed, the LOW
    # ceiling blocks it. A standing grant must not become a path to a write.
    kernel = _kernel(auto_grant_permissions=["file.write", "file.read"])
    result = kernel.execute_tool(
        ToolRequest(
            tool="file.write",
            args={"path": "/workspace/genesis_grant_test.txt", "content": "y"},
            actor="autonomy",
            role="none",
        )
    )
    assert result.status.value == "denied"
    assert not Path("/workspace/genesis_grant_test.txt").exists()


def test_env_driven_grant_is_off_by_default(monkeypatch) -> None:
    monkeypatch.delenv("GENESIS_AUTO_GRANT_PERMISSIONS", raising=False)
    cfg = GenesisConfig.from_env()
    assert cfg.security.auto_grant_permissions == []
