"""Tests for the self-improvement launcher (scripts/self_improve.py).

The launcher only *starts* an OpenHands conversation and never merges, so the
tests cover the pure pieces: the task prompt is self-contained, and a dry run
prints the prompt without touching the network.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "self_improve.py"


def _load():
    spec = importlib.util.spec_from_file_location("self_improve", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_task_prompt_is_self_contained() -> None:
    module = _load()
    text = module.TASK.format(repo="owner/repo", branch="main", topic="harden the relay")
    # Must name the repo/branch, forbid merging, and point at the real tests.
    assert "owner/repo" in text and "main" in text
    assert "harden the relay" in text
    assert "Do NOT merge" in text
    assert "tests/" in text


def test_dry_run_prints_prompt_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "PULL REQUEST" in proc.stdout or "improvement" in proc.stdout


def test_start_conversation_shape(monkeypatch) -> None:
    module = _load()
    captured: dict = {}

    def _fake_api(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"id": "task-1", "app_conversation_id": "conv-1"}

    monkeypatch.setattr(module, "_api", _fake_api)
    monkeypatch.setattr(module, "REPO", "owner/repo")
    monkeypatch.setattr(module, "BRANCH", "main")
    start = module.start_conversation("harden the relay")
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/app-conversations"
    assert captured["payload"]["selected_repository"] == "owner/repo"
    assert captured["payload"]["selected_branch"] == "main"
    assert "harden the relay" in captured["payload"]["initial_message"]["content"][0]["text"]
    assert start["app_conversation_id"] == "conv-1"


def test_slug_is_branch_safe() -> None:
    module = _load()
    slug = module._slug("Harden the relay: retries, edge-cases!")
    assert slug == "harden-the-relay-retries-edge-cases"
    assert " " not in slug and ":" not in slug


def test_open_agent_prs_filters_to_agent_branches(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_github",
        lambda *a, **k: [
            {"head": {"ref": "agent/self-improve-x"}},
            {"head": {"ref": "feature/human-work"}},
            {"head": {"ref": "agent/self-improve-y"}},
        ],
    )
    assert len(module.open_agent_prs()) == 2


def test_run_cycle_pauses_when_too_many_agent_prs(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "MAX_OPEN_PRS", 1)
    monkeypatch.setattr(module, "open_agent_prs", lambda: [{"number": 1}])
    started: list = []
    monkeypatch.setattr(module, "start_conversation", lambda topic: started.append(topic) or {})
    monkeypatch.setattr(module, "_notify", lambda text: None)
    module.run_cycle(0)
    assert started == []


def test_choose_topic_falls_back_to_rotation_without_backlog(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", "/nonexistent/backlog.jsonl")
    assert module.choose_topic(0) == module.TOPICS[0]


def test_choose_topic_prefers_highest_priority_evolution_proposal(monkeypatch, tmp_path) -> None:
    import json

    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text(
        json.dumps(
            {
                "proposals": [
                    {"title": "low", "priority": 0.2},
                    {"title": "Fix gateway: credential leak", "priority": 0.9},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    assert module.choose_topic(0) == "Fix gateway: credential leak"


def test_choose_topic_ignores_corrupt_backlog(monkeypatch, tmp_path) -> None:
    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text("not json\n", encoding="utf-8")
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    assert module.choose_topic(1) == module.TOPICS[1]


def test_choose_topic_skips_focuses_with_an_open_pr(monkeypatch, tmp_path) -> None:
    import json

    module = _load()
    backlog = tmp_path / "backlog.jsonl"
    backlog.write_text(
        json.dumps(
            {
                "proposals": [
                    {"title": "top idea", "priority": 0.9},
                    {"title": "second idea", "priority": 0.5},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", str(backlog))
    taken = {module._slug("top idea")}
    assert module.choose_topic(0, taken) == "second idea"


def test_choose_topic_rotates_when_every_focus_is_taken(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "EVOLUTION_BACKLOG", "/nonexistent/backlog.jsonl")
    taken = {module._slug(t) for t in module.TOPICS}
    # Nothing left to pick, so it must still return a usable topic.
    assert module.choose_topic(3, taken) in module.TOPICS


def test_land_pr_reuses_existing_pr_on_422(monkeypatch, tmp_path) -> None:
    module = _load()
    calls = []

    def fake_git(*args, **kwargs):
        class R:
            returncode = 0
            stderr = ""

        return R()

    def fake_github(method, path, payload=None):
        calls.append((method, path))
        if method == "POST":
            raise RuntimeError('POST /pulls -> HTTP 422: {"message":"Validation Failed"}')
        return [{"html_url": "https://github.com/o/r/pull/7"}]

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "_github", fake_github)
    url = module.land_pr("diff --git a/x b/x\n", "some focus", "app123")
    assert url == "https://github.com/o/r/pull/7"
    assert any(m == "GET" and "pulls?head=" in p for m, p in calls)


def test_land_pr_reraises_unexpected_http_error(monkeypatch) -> None:
    module = _load()

    def fake_git(*args, **kwargs):
        class R:
            returncode = 0
            stderr = ""

        return R()

    def fake_github(method, path, payload=None):
        raise RuntimeError("POST /pulls -> HTTP 500: boom")

    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module, "_github", fake_github)
    import pytest

    with pytest.raises(RuntimeError):
        module.land_pr("diff --git a/x b/x\n", "some focus", "app123")


def test_pr_number_extracts_trailing_id() -> None:
    module = _load()
    assert module._pr_number("https://github.com/o/r/pull/42") == "42"
    assert module._pr_number("https://github.com/o/r/pull/42/") == "42"
    assert module._pr_number("") == "?"


def test_process_approvals_merges_via_transport(monkeypatch) -> None:
    module = _load()
    module.GH_MERGE_TOKEN = "tok"
    replies: list[str] = []
    monkeypatch.setattr(module, "_notify", lambda text: replies.append(text))
    monkeypatch.setattr(module, "_incoming_commands", lambda: ["/approve 7"])
    monkeypatch.setattr(module, "_clear_commands", lambda: None)

    class Transport:
        def approve(self, token, reason=""):
            return f"✅ Approved & merged: fix relay ({token})"

        def reject(self, token, reason=""):
            return "rejected"

        def status(self, token):
            return "status"

        def list_open(self):
            return []

    monkeypatch.setattr(module, "_transport", lambda: Transport())
    module.process_approvals()
    assert any("Approved & merged" in r for r in replies)


def test_process_approvals_without_token_warns(monkeypatch) -> None:
    module = _load()
    replies: list[str] = []
    monkeypatch.setattr(module, "_notify", lambda text: replies.append(text))
    monkeypatch.setattr(module, "_incoming_commands", lambda: ["/approve 1"])
    monkeypatch.setattr(module, "_transport", lambda: None)
    monkeypatch.setattr(module, "_clear_commands", lambda: None)
    module.process_approvals()
    assert any("merge token" in r for r in replies)


def test_process_approvals_no_commands_is_noop(monkeypatch) -> None:
    module = _load()
    called = {"clear": False}
    monkeypatch.setattr(module, "_incoming_commands", lambda: [])
    monkeypatch.setattr(module, "_clear_commands", lambda: called.update(clear=True))
    module.process_approvals()
    assert called["clear"] is False

