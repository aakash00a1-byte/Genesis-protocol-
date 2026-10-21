#!/usr/bin/env python3
"""Give the Genesis agent a job: improve the Genesis repo itself.

Level B self-improvement. This script starts ONE OpenHands Cloud conversation
whose task is to review this repository, make a single small, safe, high-value
change on its own branch, run the relevant tests, and open a pull request.

It deliberately does NOT merge. A human reviews the PR and merges it; the merge
then triggers the normal auto-deploy workflow. Nothing reaches production
without a review gate.

Env:
  OPENHANDS_API_KEY       required; OpenHands Cloud API key
  SELF_IMPROVE_REPO       default aakash00a1-byte/Genesis-protocol-
  SELF_IMPROVE_BRANCH     default main
  SELF_IMPROVE_MODEL      optional; OpenHands LLM model override
  OH_BASE_URL             default https://app.all-hands.dev

Exit codes: 0 on a conversation that reached READY, 1 on any failure, so a
scheduled run surfaces problems instead of hiding them.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OH_BASE_URL", "https://app.all-hands.dev").rstrip("/")
API_KEY = os.environ.get("OPENHANDS_API_KEY", "").strip()
REPO = os.environ.get("SELF_IMPROVE_REPO", "aakash00a1-byte/Genesis-protocol-").strip()
BRANCH = os.environ.get("SELF_IMPROVE_BRANCH", "main").strip()
MODEL = os.environ.get("SELF_IMPROVE_MODEL", "").strip()

POLL_SECONDS = 15
POLL_TIMEOUT_SECONDS = 900

TASK = """\
You are working on the Genesis Protocol repository ({repo}), branch {branch}.

Goal: make ONE small, safe, high-value improvement to this repository.

Rules (important):
- Pick a single, focused change. Small is good: a bug fix, a missing test, a
  doc fix, a clearer error message, a small hardening. Do NOT attempt a large
  refactor or a new feature.
- Run the relevant tests before you finish. The relay tests are:
  `python3 -m pytest tests/test_relay_loop.py tests/test_workflows_static.py -q`
  and lint with `python3 -m ruff check scripts/ web/`.
- Work on a NEW branch (e.g. `agent/self-improve-<short-topic>`).
- Commit with a clear message, push the branch, and open a PULL REQUEST against
  `{branch}`.
- Do NOT merge the pull request. Do NOT push to `{branch}` directly.
- In the PR description, state what changed, why, and how you verified it.

When you are done, report the pull request URL.
"""


def _api(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed OpenHands host
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    return json.loads(body or b"{}")


def _log(msg: str) -> None:
    print(f"[self-improve] {msg}", flush=True)


def start_conversation() -> dict:
    payload: dict = {
        "initial_message": {
            "content": [{"type": "text", "text": TASK.format(repo=REPO, branch=BRANCH)}]
        },
        "selected_repository": REPO,
        "selected_branch": BRANCH,
        "title": "Genesis self-improvement",
    }
    if MODEL:
        payload["llm_model"] = MODEL
    return _api("POST", "/api/v1/app-conversations", payload)


def poll_until_ready(start: dict) -> str | None:
    """Return the app_conversation_id once the start-task is ready."""
    app_id = start.get("app_conversation_id")
    if app_id:
        return app_id
    task_id = start.get("id")
    if not task_id:
        _log(f"unexpected start response keys: {sorted(start)}")
        return None
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            task = _api(
                "GET", f"/api/v1/app-conversations/start-tasks?ids={task_id}"
            )
        except RuntimeError as exc:
            _log(str(exc))
            continue
        if isinstance(task, list):
            item = task[0] if task else {}
        else:
            items = task.get("items") or [task]
            item = items[0] if items else {}
        status = str(item.get("status", "")).upper()
        _log(f"start-task {task_id}: {status or 'unknown'}")
        if item.get("app_conversation_id"):
            return item["app_conversation_id"]
        if status in {"ERROR", "FAILED", "CANCELLED"}:
            return None
    _log("timed out waiting for the conversation to start")
    return None


def main() -> int:
    if "--dry-run" in sys.argv:
        _log(f"dry run: would start a conversation on {REPO}@{BRANCH}")
        print(TASK.format(repo=REPO, branch=BRANCH))
        return 0
    if not API_KEY:
        _log("OPENHANDS_API_KEY is not set")
        return 1
    _log(f"starting a self-improvement conversation on {REPO}@{BRANCH}")
    try:
        start = start_conversation()
    except RuntimeError as exc:
        _log(f"could not start the conversation: {exc}")
        return 1
    _log(f"start response: {json.dumps(start)[:300]}")
    app_id = poll_until_ready(start)
    if not app_id:
        _log("the conversation did not become ready")
        return 1
    ui_url = f"{BASE_URL}/canvas/conversations/{app_id}"
    _log(f"conversation ready: {app_id}")
    print(f"conversation_ui_url={ui_url}")
    print(f"app_conversation_id={app_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
