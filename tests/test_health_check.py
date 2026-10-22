"""Tests for scripts/health_check.py.

The checker answers "is anything broken?" with three independent checks. These
tests cover the pieces that can run offline: the import check must really walk
every package, and the report must be truthful when a check fails.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "health_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("health_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_imports_all_pass() -> None:
    """Every genesis_protocol package must import on a clean checkout."""
    ok, detail = _load().check_imports()
    assert ok, detail
    assert "import OK" in detail


def test_import_check_reports_a_broken_package(monkeypatch) -> None:
    """A package that raises on import must be reported, not swallowed."""
    module = _load()

    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "genesis_protocol.voice":
            raise ImportError("boom")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    ok, detail = module.check_imports()
    assert not ok
    assert "genesis_protocol.voice" in detail


def test_run_checks_offline_reports_imports(monkeypatch) -> None:
    module = _load()
    ok, results = module.run_checks(do_net=False)
    assert ok
    assert len(results) == 1
    assert "modules:" in results[0][1]


def test_workflows_skipped_without_token(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "GITHUB_TOKEN", "")
    ok, detail = module.check_workflows()
    assert ok
    assert "skipped" in detail


def test_redact_hides_secrets(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "TELEGRAM_BOT_TOKEN", "123:ABC")
    assert "ABC" not in module._redact("token 123:ABC here")
