"""The autonomy loop drives read-only recon through the full authority gate.

Proves the wiring end to end: with autonomy enabled the loop's read-only
recon is auto-approved (no per-call human), it still travels the gateway, a
write is still denied, and with autonomy disabled nothing is granted.
"""
from __future__ import annotations

import tempfile

from genesis.autonomy import AutonomousLoop
from genesis.config.settings import AutonomyConfig, Env, GenesisConfig
from genesis.tools.gateway import ToolRequest


def _cfg(**autonomy) -> GenesisConfig:
    base = {
        "enabled": True,
        "max_iterations": 2,
        "max_retries_per_step": 0,
        "max_wall_clock_seconds": 20.0,
        "step_timeout_seconds": 5.0,
        "checkpoint_dir": tempfile.mkdtemp(prefix="genesis-recon-"),
    }
    base.update(autonomy)
    return GenesisConfig(
        env=Env.TESTING, offline=True, autonomy=AutonomyConfig(**base)
    )


def test_enabled_loop_auto_approves_read_only_recon() -> None:
    cfg = _cfg()
    loop = AutonomousLoop(_build(cfg), cfg.autonomy)
    # role="none" grants nothing by role, so a granted recon proves the
    # standing grant (not the role) is what approves it.
    result = loop.run("list the workspace and show git status", role="none")
    assert result.status.value == "succeeded", result.errors
    assert result.recon["file.list"]["granted"] is True
    assert result.recon["git.status"]["granted"] is True
    assert result.recon["git.log"]["granted"] is True


def test_disabled_autonomy_grants_nothing() -> None:
    cfg = _cfg(enabled=False)
    kernel = _build(cfg)
    # No standing grant is configured, so a read from the autonomy actor is
    # denied by the gate (the loop would not even run when disabled).
    result = kernel.execute_tool(
        ToolRequest(tool="file.list", args={}, actor="autonomy", role="none")
    )
    assert result.status.value == "denied"


def test_recon_never_covers_a_write() -> None:
    cfg = _cfg()
    kernel = _build(cfg)
    # Even with autonomy enabled, a write is MEDIUM risk and stays denied.
    result = kernel.execute_tool(
        ToolRequest(
            tool="file.write",
            args={"path": "/workspace/genesis_recon_write.txt", "content": "x"},
            actor="autonomy",
            role="none",
        )
    )
    assert result.status.value == "denied"


def test_recon_is_scoped_to_the_run_actor() -> None:
    cfg = _cfg()
    kernel = _build(cfg)
    result = kernel.execute_tool(
        ToolRequest(tool="file.list", args={}, actor="intruder", role="none")
    )
    assert result.status.value == "denied"


def test_custom_recon_list_is_honoured() -> None:
    cfg = _cfg()
    kernel = _build(cfg)
    loop = AutonomousLoop(
        kernel,
        cfg.autonomy,
        recon=[ToolRequest(tool="file.list", args={})],
    )
    result = loop.run("just list files", role="none")
    assert set(result.recon) == {"file.list"}
    assert result.recon["file.list"]["granted"] is True


def test_recon_outcome_is_persisted() -> None:
    cfg = _cfg()
    loop = AutonomousLoop(_build(cfg), cfg.autonomy)
    result = loop.run("list the workspace", role="none")
    state = loop.store.load(result.run_id)
    assert state.recon == result.recon
    assert state.recon["file.list"]["granted"] is True


def _build(cfg: GenesisConfig):
    from genesis.bootstrap import build

    return build(cfg)
