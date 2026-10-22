#!/usr/bin/env python3
"""Give the Genesis agent a continuous job: keep improving the Genesis repo.

A long-running loop (like the Telegram relay) that, every cycle, starts ONE
OpenHands Cloud conversation to make a single small, safe change on its own
branch. Because the agent sandbox has a read-only GitHub credential, this
harness lands the result: it pulls the agent's commit out of the sandbox,
applies it on a fresh branch, pushes, and opens a pull request. It then sends a
Telegram notification with the PR link.

It deliberately does NOT merge. A human reviews the PR and merges it; the merge
then triggers the normal auto-deploy workflow. Nothing reaches production
without a review gate.

Env:
  OPENHANDS_API_KEY            required; OpenHands Cloud API key
  GITHUB_TOKEN                 required to push branches / open PRs
  SELF_IMPROVE_REPO            default aakash00a1-byte/Genesis-protocol-
  SELF_IMPROVE_BRANCH          default main
  SELF_IMPROVE_MODEL           optional; OpenHands LLM model override
  SELF_IMPROVE_INTERVAL_SECONDS default 2700 (one improvement every 45 min)
  SELF_IMPROVE_RUN_SECONDS     default 19800 (the loop runs ~5h30m, like relay)
  SELF_IMPROVE_MAX_OPEN_PRS    default 5 (pause when this many agent PRs await)
  TELEGRAM_BOT_TOKEN / TELEGRAM_ADMIN_ID   optional; send progress pings
  OH_BASE_URL                  default https://app.all-hands.dev

Flags:
  --once      run exactly one cycle and exit (for manual/test runs)
  --dry-run   print the task prompt and exit without touching the network
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = os.environ.get("OH_BASE_URL", "https://app.all-hands.dev").rstrip("/")
API_KEY = os.environ.get("OPENHANDS_API_KEY", "").strip()
REPO = os.environ.get("SELF_IMPROVE_REPO", "aakash00a1-byte/Genesis-protocol-").strip()
BRANCH = os.environ.get("SELF_IMPROVE_BRANCH", "main").strip()
MODEL = os.environ.get("SELF_IMPROVE_MODEL", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()

CYCLE_INTERVAL_SECONDS = int(os.environ.get("SELF_IMPROVE_INTERVAL_SECONDS", "2700"))
RUN_SECONDS = int(os.environ.get("SELF_IMPROVE_RUN_SECONDS", str(5 * 3600 + 30 * 60)))
MAX_OPEN_PRS = int(os.environ.get("SELF_IMPROVE_MAX_OPEN_PRS", "5"))
POLL_SECONDS = 15
POLL_TIMEOUT_SECONDS = 900
# A conversation can take a while; the earlier one took ~50 minutes. Allow 45
# minutes per cycle and make it tunable.
RUN_TIMEOUT_SECONDS = int(os.environ.get("SELF_IMPROVE_CYCLE_TIMEOUT_SECONDS", "2700"))

# Rotated by wall-clock so a fresh topic is picked each cycle without state.
TOPICS: list[str] = [
    "harden the Telegram relay (scripts/relay_loop.py): retries, error handling, edge cases",
    "add a missing regression test for a recent fix",
    "improve error messages and logging in scripts/ or web/",
    "fix a bug you can reproduce in the relay or the web app",
    "tighten input validation in web/app.py",
    "improve documentation in AGENTS.md or docs/",
    "reduce duplication across scripts/ and web/",
    "add a missing test for a web/app.py endpoint",
]

TASK = """\
You are working on the Genesis Protocol repository ({repo}), branch {branch}.

Goal: make ONE small, safe, high-value improvement, then STOP. Focus this cycle on:
  {topic}

Be fast and decisive (aim to finish in under 10 minutes):
- Spend at most a few minutes exploring. Do NOT read the whole repository.
- Pick the first small, clear improvement you find in the focus area. One file,
  a handful of lines. Do NOT attempt a large refactor or a new feature.
- Run the focused tests for what you touched, e.g.
  `python3 -m pytest tests/test_relay_loop.py tests/test_workflows_static.py -q`
  and lint with `python3 -m ruff check scripts/ web/`.
- As soon as your change passes, COMMIT it on a new branch and STOP. Do not keep
  exploring or polishing.
- Do NOT merge anything and do NOT push to `{branch}` directly.
- You do NOT have push access and cannot open the pull request; the harness does
  that for you. Do not run `git push`. Just leave one clean commit.

When you are done, report the branch name, the commit sha, and a one-line
summary of what changed and how you verified it.
"""


def _log(msg: str) -> None:
    print(f"[self-improve] {msg}", flush=True)


def _api(method: str, path: str, payload: dict | None = None) -> object:
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


def _github(method: str, path: str, payload: dict | None = None) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed GitHub host
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc
    return json.loads(body or b"{}")


def _notify(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        return
    try:
        _api_raw(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            {"chat_id": TELEGRAM_ADMIN_ID, "text": text[:3900], "disable_web_page_preview": True},
        )
    except Exception as exc:  # noqa: BLE001 - a failed ping must not stop the loop
        _log(f"telegram notify failed: {type(exc).__name__}")


def _api_raw(url: str, payload: dict) -> None:
    req = urllib.request.Request(  # noqa: S310 - fixed service hosts
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30):  # noqa: S310
        pass


def start_conversation(topic: str) -> dict:
    payload: dict = {
        "initial_message": {
            "content": [{"type": "text", "text": TASK.format(repo=REPO, branch=BRANCH, topic=topic)}]
        },
        "selected_repository": REPO,
        "selected_branch": BRANCH,
        "title": f"Genesis self-improvement: {topic[:40]}",
    }
    if MODEL:
        payload["llm_model"] = MODEL
    return _api("POST", "/api/v1/app-conversations", payload)  # type: ignore[return-value]


def _conversation(app_id: str) -> dict:
    resp = _api("GET", f"/api/v1/app-conversations?ids={app_id}")
    if isinstance(resp, list):
        return resp[0] if resp else {}
    items = resp.get("items") if isinstance(resp, dict) else None  # type: ignore[union-attr]
    return (items or [resp])[0]


def poll_until_ready(start: dict) -> str | None:
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
            task = _api("GET", f"/api/v1/app-conversations/start-tasks?ids={task_id}")
        except RuntimeError as exc:
            _log(str(exc))
            continue
        if isinstance(task, list):
            item = task[0] if task else {}
        else:
            items = task.get("items") or [task]
            item = items[0] if items else {}
        status = str(item.get("status", "")).upper()
        _log(f"start-task: {status or 'unknown'}")
        if item.get("app_conversation_id"):
            return item["app_conversation_id"]
        if status in {"ERROR", "FAILED", "CANCELLED"}:
            return None
    _log("timed out waiting for the conversation to start")
    return None


def wait_until_finished(app_id: str) -> bool:
    deadline = time.time() + RUN_TIMEOUT_SECONDS
    while time.time() < deadline:
        time.sleep(POLL_SECONDS)
        try:
            conv = _conversation(app_id)
        except RuntimeError as exc:
            _log(str(exc))
            continue
        status = str(conv.get("execution_status", "")).lower()
        if status in {"finished", "error", "stopped"}:
            _log(f"conversation finished: {status}")
            return status == "finished"
    _log("timed out waiting for the conversation to finish")
    return False


def _agent_server(app_id: str) -> tuple[str, str] | None:
    conv = _conversation(app_id)
    key = conv.get("session_api_key")
    url = conv.get("agent_server_url")
    if not url:
        conv_url = conv.get("conversation_url") or ""
        if "/api/conversations" in conv_url:
            url = conv_url.rsplit("/api/conversations", 1)[0]
    if not url or not key:
        return None
    return url.rstrip("/"), key


def _sandbox_bash(base: str, key: str, command: str) -> str:
    req = urllib.request.Request(  # noqa: S310 - sandbox host from the API
        f"{base}/api/bash/execute_bash_command",
        data=json.dumps({"command": command}).encode(),
        method="POST",
        headers={"X-Session-API-Key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.loads(resp.read() or b"{}").get("stdout", "")


def get_patch(app_id: str) -> str | None:
    conn = _agent_server(app_id)
    if not conn:
        _log("no sandbox connection info; cannot fetch the patch")
        return None
    base, key = conn
    workdir = f"/workspace/project/{REPO.split('/')[-1]}"
    try:
        patch = _sandbox_bash(base, key, f"cd {workdir} && git format-patch {BRANCH}..HEAD --stdout")
        if not patch.strip():
            patch = _sandbox_bash(base, key, f"cd {workdir} && git diff {BRANCH}...HEAD")
    except Exception as exc:  # noqa: BLE001
        _log(f"could not read the patch from the sandbox: {type(exc).__name__}")
        return None
    return patch if patch.strip() else None


def _slug(topic: str) -> str:
    keep = "".join(c if c.isalnum() else "-" for c in topic.lower())
    while "--" in keep:
        keep = keep.replace("--", "-")
    return keep.strip("-")[:40].strip("-") or "improve"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=os.getcwd()
    )


def open_agent_prs() -> list[dict]:
    prs = _github("GET", f"/repos/{REPO}/pulls?state=open&per_page=100")
    if not isinstance(prs, list):
        return []
    return [p for p in prs if str(p.get("head", {}).get("ref", "")).startswith("agent/")]


def land_pr(patch: str, topic: str, app_id: str) -> str | None:
    branch = f"agent/self-improve-{_slug(topic)}"
    _git("checkout", "-B", branch, f"origin/{BRANCH}")
    patch_file = "/tmp/agent.patch"
    with open(patch_file, "w") as fh:
        fh.write(patch)
    applied = _git("apply", "--index", patch_file)
    if applied.returncode != 0:
        _log(f"patch did not apply cleanly: {applied.stderr.strip()[:200]}")
        return None
    _git("commit", "-m", f"chore(agent): {topic}\n\nProposed by the Genesis self-improvement agent (OpenHands conversation {app_id}); landed by the harness for human review.\n\nCo-authored-by: openhands <openhands@all-hands.dev>")
    pushed = _git("push", "-f", "origin", branch)
    if pushed.returncode != 0:
        _log(f"push failed: {pushed.stderr.strip()[:200]}")
        return None
    body = (
        f"## Agent-proposed improvement\n\n**Focus:** {topic}\n\n"
        f"Proposed by the Genesis self-improvement agent (OpenHands conversation `{app_id}`). "
        "The agent sandbox has a read-only GitHub credential, so the harness landed the commit.\n\n"
        "### Review gate\nThis PR is intentionally **not** merged. Merging it triggers "
        "`.github/workflows/deploy-space.yml`, which mirrors `main` to the live HF Space.\n\n"
        "---\n_This pull request was created by an AI agent (OpenHands) on behalf of the repository owner._"
    )
    pr = _github(
        "POST",
        f"/repos/{REPO}/pulls",
        {"title": f"chore(agent): {topic}", "head": branch, "base": BRANCH, "body": body},
    )
    if isinstance(pr, dict) and pr.get("html_url"):
        return pr["html_url"]
    return None


def run_cycle(index: int) -> None:
    topic = TOPICS[index % len(TOPICS)]
    waiting = open_agent_prs()
    if len(waiting) >= MAX_OPEN_PRS:
        _log(f"{len(waiting)} agent PRs already await review; skipping this cycle")
        _notify(f"🧠 Genesis agent: {len(waiting)} PRs await review, pausing new work.")
        return
    _log(f"cycle {index}: {topic}")
    try:
        start = start_conversation(topic)
    except RuntimeError as exc:
        _log(f"could not start the conversation: {exc}")
        return
    app_id = poll_until_ready(start)
    if not app_id:
        _log("conversation did not become ready")
        return
    _log(f"conversation {app_id} ready")
    if not wait_until_finished(app_id):
        _log("conversation did not finish cleanly")
        return
    patch = get_patch(app_id)
    if not patch:
        _log("agent produced no patch")
        _notify(f"🧠 Genesis agent cycle '{topic[:50]}': no change produced.")
        return
    pr_url = land_pr(patch, topic, app_id)
    if pr_url:
        _log(f"opened PR: {pr_url}")
        _notify(f"🧠 Genesis agent ne ek improvement bheja:\n{topic[:80]}\n\nPR: {pr_url}")
    else:
        _log("could not land the patch as a PR")
        _notify(f"🧠 Genesis agent cycle '{topic[:50]}': patch did not apply; skipped.")


def main() -> int:
    if "--dry-run" in sys.argv:
        print(TASK.format(repo=REPO, branch=BRANCH, topic=TOPICS[0]))
        return 0
    if not API_KEY:
        _log("OPENHANDS_API_KEY is not set")
        return 1
    if "--once" in sys.argv:
        run_cycle(int(time.time() // max(CYCLE_INTERVAL_SECONDS, 1)))
        return 0
    if not GITHUB_TOKEN:
        _log("GITHUB_TOKEN is not set; cannot open PRs")
        return 1
    _log(f"starting continuous self-improvement every {CYCLE_INTERVAL_SECONDS}s for {RUN_SECONDS}s")
    _notify("🧠 Genesis agent 24x7 loop start: main improvements karta rahunga.")
    started = time.monotonic()
    index = int(time.time() // max(CYCLE_INTERVAL_SECONDS, 1))
    while time.monotonic() - started < RUN_SECONDS:
        run_cycle(index)
        index += 1
        # Sleep until the next cycle, but stop early at the run deadline.
        remaining = RUN_SECONDS - (time.monotonic() - started)
        time.sleep(max(0.0, min(CYCLE_INTERVAL_SECONDS, remaining)))
    _log("self-improvement loop finished; the next scheduled run takes over")
    return 0


if __name__ == "__main__":
    sys.exit(main())

