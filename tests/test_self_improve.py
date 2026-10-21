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
    text = module.TASK.format(repo="owner/repo", branch="main")
    # Must name the repo/branch, forbid merging, and point at the real tests.
    assert "owner/repo" in text and "main" in text
    assert "Do NOT merge" in text
    assert "tests/test_relay_loop.py" in text
    assert "PULL REQUEST" in text


def test_dry_run_prints_prompt_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    assert "dry run" in proc.stdout
    assert "PULL REQUEST" in proc.stdout


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
    start = module.start_conversation()
    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/app-conversations"
    assert captured["payload"]["selected_repository"] == "owner/repo"
    assert captured["payload"]["selected_branch"] == "main"
    assert start["app_conversation_id"] == "conv-1"
