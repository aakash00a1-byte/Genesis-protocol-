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


def test_missing_third_party_dep_is_not_a_failure(monkeypatch) -> None:
    """A bare runner has no optional deps; that is not broken code."""
    module = _load()

    real_import = importlib.import_module

    def fake_import(name, *args, **kwargs):
        if name == "genesis_protocol.vision":
            raise ModuleNotFoundError("No module named 'PIL'", name="PIL")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    ok, detail = module.check_imports()
    assert ok
    assert "PIL" in detail


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


def test_workflows_header_is_truthful_for_non_success(monkeypatch) -> None:
    """in_progress / action_required must never be reported as "all green"."""
    module = _load()
    monkeypatch.setattr(module, "GITHUB_TOKEN", "tok")

    runs = {
        "ci.yml": "action_required",
        "deploy-space.yml": "success",
        "self-improve.yml": "success",
        "keepalive.yml": "in_progress",
        "heartbeat.yml": "success",
        "register-webhook.yml": "success",
    }

    def fake_github(path):
        wf = path.split("/workflows/")[1].split("/")[0]
        return {"workflow_runs": [{"conclusion": None if runs[wf] == "in_progress" else runs[wf],
                                   "status": runs[wf]}]}

    monkeypatch.setattr(module, "_github", fake_github)
    ok, detail = module.check_workflows()
    assert ok, "a non-failure must not page the owner"
    assert "all green" not in detail
    assert "not green" in detail
    assert "ci.yml" in detail and "keepalive.yml" in detail


def test_workflows_header_green_only_when_all_succeed(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "GITHUB_TOKEN", "tok")

    def fake_github(path):
        return {"workflow_runs": [{"conclusion": "success", "status": "completed"}]}

    monkeypatch.setattr(module, "_github", fake_github)
    ok, detail = module.check_workflows()
    assert ok
    assert "all green" in detail


def test_workflows_failure_still_pages(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "GITHUB_TOKEN", "tok")

    def fake_github(path):
        wf = path.split("/workflows/")[1].split("/")[0]
        conclusion = "failure" if wf == "deploy-space.yml" else "success"
        return {"workflow_runs": [{"conclusion": conclusion, "status": "completed"}]}

    monkeypatch.setattr(module, "_github", fake_github)
    ok, detail = module.check_workflows()
    assert not ok
    assert "1 failing" in detail
    assert "deploy-space.yml" in detail


def test_space_cold_start_is_retried(monkeypatch) -> None:
    """A first-attempt timeout must not be reported as unreachable."""
    module = _load()
    monkeypatch.setattr(module, "HF_SPACE_URL", "https://space.invalid")
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    class _Resp:
        def read(self):
            return b'{"status": "healthy"}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("cold start")
        return _Resp()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    ok, detail = module.check_space(attempts=3, backoff_seconds=0)
    assert ok, detail
    assert "healthy" in detail
    assert calls["n"] == 2


def test_space_still_fails_when_really_down(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "HF_SPACE_URL", "https://space.invalid")
    monkeypatch.setattr(module.time, "sleep", lambda _s: None)

    def fake_urlopen(req, timeout=0):
        raise TimeoutError("down")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)
    ok, detail = module.check_space(attempts=2, backoff_seconds=0)
    assert not ok
    assert "unreachable" in detail
    assert "2 attempts" in detail
