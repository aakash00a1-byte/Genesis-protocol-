"""Tests for the acceptance gate (tests + security checks before accepting).

The runner test invokes the *real* pytest on a tiny throwaway test file, so the
gate is exercised against a real test process rather than a mock.
"""
from __future__ import annotations

import sys

from genesis.autonomy.acceptance import AcceptanceGate
from genesis.autonomy.loop import AutonomousLoop, RunStatus
from genesis.bootstrap import build
from genesis.config.settings import AutonomyConfig, Env, GenesisConfig


def _cfg(tmp_path, **overrides) -> GenesisConfig:
    base = {
        "enabled": True,
        "max_iterations": 3,
        "max_retries_per_step": 1,
        "max_wall_clock_seconds": 30.0,
        "step_timeout_seconds": 5.0,
        "checkpoint_dir": str(tmp_path),
    }
    base.update(overrides)
    return GenesisConfig(
        env=Env.TESTING, offline=True, autonomy=AutonomyConfig(**base)
    )


def test_secret_in_change_is_rejected() -> None:
    gate = AcceptanceGate()
    report = gate.evaluate(
        {"genesis/x.py": 'API_KEY = "sk-abcdef0123456789abcdef"'}
    )
    assert not report.accepted
    assert report.secret_findings == ["genesis/x.py"]
    assert "secret" in report.reasons[0]


def test_clean_change_is_accepted_without_runner() -> None:
    gate = AcceptanceGate()
    report = gate.evaluate({"genesis/x.py": "def f():\n    return 1\n"})
    assert report.accepted
    assert report.tests_run is False


def test_required_tests_without_runner_is_rejected() -> None:
    gate = AcceptanceGate(require_tests=True)
    report = gate.evaluate({"genesis/x.py": "x = 1\n"})
    assert not report.accepted
    assert "no runner" in report.reasons[0]


def test_real_pytest_runner_passes_and_fails(tmp_path) -> None:
    good = tmp_path / "test_good.py"
    good.write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    bad = tmp_path / "test_bad.py"
    bad.write_text("def test_no():\n    assert 1 + 1 == 3\n")

    runner = AcceptanceGate.command_runner(
        f"{sys.executable} -m pytest {good} -q"
    )
    assert AcceptanceGate(test_runner=runner).evaluate({"a.py": "x=1"}).accepted

    failing = AcceptanceGate.command_runner(
        f"{sys.executable} -m pytest {bad} -q"
    )
    report = AcceptanceGate(test_runner=failing).evaluate({"a.py": "x=1"})
    assert not report.accepted
    assert report.tests_run and not report.tests_passed


def test_loop_rejects_change_with_secret(tmp_path) -> None:
    kernel = build(_cfg(tmp_path))
    gate = AcceptanceGate()
    loop = AutonomousLoop(
        kernel,
        kernel.config.autonomy,
        acceptance=gate,
        changes={"genesis/x.py": 'TOKEN = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"'},
    )
    result = loop.run("implement the change", role="admin")
    assert result.status is RunStatus.FAILED
    assert result.ok is False
    types = [e["event_type"] for e in kernel.audit.events()]
    assert "autonomy.change_rejected" in types


def test_loop_accepts_clean_change(tmp_path) -> None:
    kernel = build(_cfg(tmp_path))
    gate = AcceptanceGate()
    loop = AutonomousLoop(
        kernel,
        kernel.config.autonomy,
        acceptance=gate,
        changes={"genesis/x.py": "def f():\n    return 42\n"},
    )
    result = loop.run("implement the change", role="admin")
    assert result.status is RunStatus.SUCCEEDED
    assert result.ok is True
