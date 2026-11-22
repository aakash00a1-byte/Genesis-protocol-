"""Tests for the CI-aware wiring inside the self-improvement loop.

The loop used to pause on a bare count of open PRs. These tests pin the new
behaviour: capacity comes from real CI state, a blocked PR is reported per PR,
and a PR is never opened with an identity whose runs GitHub will hold.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "self_improve.py"
HEAD = "c226f92223e0"
BASE = "410069de52e9"


def _load():
    spec = importlib.util.spec_from_file_location("self_improve_ci", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pr(number, sha=HEAD):
    return {
        "number": number,
        "head": {"ref": f"agent/self-improve-{number}", "sha": sha},
        "base": {"sha": BASE},
        "body": f"landed commit: `{sha}`",
    }


def _install(monkeypatch, module, *, checks, runs, main_sha=BASE):
    """Route the harness's GitHub reads to fixed payloads, no network."""

    def fake_github(method, path, data=None):
        if "/git/ref/heads/" in path:
            return {"object": {"sha": main_sha}}
        if path.endswith("/check-runs"):
            return {"check_runs": checks}
        if "/actions/runs" in path:
            return {"workflow_runs": runs}
        return {}

    monkeypatch.setattr(module, "_github", fake_github)


def test_health_reads_real_ci_state(monkeypatch):
    module = _load()
    _install(
        monkeypatch,
        module,
        checks=[{"name": "test", "conclusion": "success"}],
        runs=[{"id": 1, "conclusion": "success"}],
    )
    healths = module._pr_health([_pr(90)])
    assert len(healths) == 1
    assert healths[0].state == "READY_FOR_REVIEW"


def test_held_run_is_detected_through_the_harness(monkeypatch):
    module = _load()
    _install(
        monkeypatch,
        module,
        checks=[],
        runs=[{"id": 7, "conclusion": "action_required"}],
    )
    healths = module._pr_health([_pr(80)])
    assert healths[0].state == "ACTION_REQUIRED"
    assert healths[0].needs_owner


def test_unreadable_ci_is_not_treated_as_green(monkeypatch):
    """A failed API read must degrade to "no evidence", never to success."""
    module = _load()

    def boom(method, path, data=None):
        if "/git/ref/heads/" in path:
            return {"object": {"sha": BASE}}
        raise RuntimeError("api down")

    monkeypatch.setattr(module, "_github", boom)
    healths = module._pr_health([_pr(80)])
    assert healths[0].state != "READY_FOR_REVIEW"
    assert not healths[0].mergeable


def test_missing_model_degrades_to_the_old_count(monkeypatch):
    """An older checkout without ci_health must not crash the loop."""
    module = _load()
    import builtins

    real_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if "ci_health" in name:
            raise ImportError("simulated missing module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)
    assert module._pr_health([_pr(80)]) == []


def test_run_cycle_pauses_when_capacity_is_full(monkeypatch):
    module = _load()
    notes: list[str] = []
    monkeypatch.setattr(module, "open_agent_prs", lambda: [_pr(n) for n in range(1, 6)])
    monkeypatch.setattr(module, "_notify", notes.append)
    monkeypatch.setattr(
        module,
        "_pr_health",
        lambda waiting: [_ready(n) for n in range(1, 6)],
    )
    monkeypatch.setattr(
        module, "start_conversation", lambda topic: (_ for _ in ()).throw(AssertionError("must not start"))
    )
    module.run_cycle(1)
    assert any("paused" in n or "capacity" in n for n in notes)


def _ready(number):
    from genesis_protocol.evolution.ci_health import classify_pr

    return classify_pr(
        number=number,
        branch=f"agent/x{number}",
        head_sha=HEAD,
        base_sha=BASE,
        main_sha=BASE,
        body=f"landed commit: `{HEAD}`",
        check_runs=[{"name": "test", "conclusion": "success"}],
        runs=[{"id": number, "conclusion": "success"}],
    )


def _blocked(number):
    from genesis_protocol.evolution.ci_health import classify_pr

    return classify_pr(
        number=number,
        branch=f"agent/x{number}",
        head_sha=HEAD,
        base_sha=BASE,
        main_sha=BASE,
        body=f"landed commit: `{HEAD}`",
        check_runs=[],
        runs=[{"id": number, "conclusion": "action_required"}],
    )


def test_run_cycle_reports_each_blocked_pr_truthfully(monkeypatch):
    """The owner gets per-PR status, not a blanket "N PRs await review"."""
    module = _load()
    notes: list[str] = []
    monkeypatch.setattr(module, "open_agent_prs", lambda: [_pr(80), _pr(81)])
    monkeypatch.setattr(module, "_notify", notes.append)
    monkeypatch.setattr(module, "_pr_health", lambda waiting: [_blocked(80), _blocked(81)])
    monkeypatch.setattr(module, "start_conversation", lambda topic: {"id": "x"})
    # Two blocked PRs leave capacity, so the cycle proceeds and would poll the
    # real API. Stop it at the first poll: this test is about the messages.
    monkeypatch.setattr(module, "poll_until_ready", lambda start: None)
    module.run_cycle(1)
    joined = "\n".join(notes)
    assert "#80" in joined and "#81" in joined
    assert "✅" not in joined


def test_run_cycle_starts_work_when_blocked_prs_do_not_fill_capacity(monkeypatch):
    """The deadlock fix, exercised through run_cycle rather than the model."""
    module = _load()
    started: list[str] = []
    monkeypatch.setattr(module, "open_agent_prs", lambda: [_pr(80), _pr(81)])
    monkeypatch.setattr(module, "_notify", lambda text: None)
    monkeypatch.setattr(module, "_pr_health", lambda waiting: [_blocked(80), _blocked(81)])
    monkeypatch.setattr(module, "start_conversation", lambda topic: started.append(topic) or {"id": "x"})
    monkeypatch.setattr(module, "poll_until_ready", lambda start: None)
    module.run_cycle(1)
    assert started, "blocked PRs must not consume every slot"
