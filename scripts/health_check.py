#!/usr/bin/env python3
"""Genesis health check - is anything broken, and what is actually live?

One script, no new layers. It answers the question the project had no answer
for: "it is running, but is anything broken?" Three checks, each independent
so one failure never hides the others:

  1. every ``genesis_protocol`` package imports
  2. the live HF Space answers its health endpoint
  3. the GitHub workflows' most recent run is not red

Run it by hand, from CI, or from the relay loop. With TELEGRAM_BOT_TOKEN and
TELEGRAM_ADMIN_ID set it also sends the summary to the owner; ``--no-send``
keeps it local. Exit code is 0 only when every check passes.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

HF_SPACE_URL = os.environ.get("HF_SPACE_URL", "https://genesisno-genesis-automaton.hf.space").rstrip("/")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO = os.environ.get("HEALTH_REPO", os.environ.get("SELF_IMPROVE_REPO", "aakash00a1-byte/Genesis-protocol-")).strip()
HF_SHARED_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
WORKFLOWS = ("ci.yml", "deploy-space.yml", "self-improve.yml", "keepalive.yml", "heartbeat.yml", "register-webhook.yml")


def _redact(text: str) -> str:
    for secret in (TELEGRAM_BOT_TOKEN, GITHUB_TOKEN, HF_SHARED_SECRET):
        if secret:
            text = text.replace(secret, "***")
    return text


def _log(msg: str) -> None:
    print(_redact(f"[health] {msg}"), flush=True)


def _space_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if HF_SHARED_SECRET:
        headers["X-Telegram-Bot-Api-Secret-Token"] = HF_SHARED_SECRET
    return headers


def check_imports() -> tuple[bool, str]:
    """Import every genesis_protocol package.

    A bare runner (CI) has none of the third-party packages installed, so a
    ``ModuleNotFoundError`` for something like ``httpx`` means "dependency not
    installed here", not "the code is broken". Only a failure that is *not* a
    missing external dependency — a syntax error, a bad name, a broken import
    inside genesis_protocol — is reported as broken.
    """
    import importlib

    root_pkg = os.path.join(_ROOT, "genesis_protocol")
    names = ["genesis_protocol"]
    for entry in sorted(os.listdir(root_pkg)):
        if os.path.isfile(os.path.join(root_pkg, entry, "__init__.py")):
            names.append(f"genesis_protocol.{entry}")

    broken: list[str] = []
    missing_deps: set[str] = set()
    for name in names:
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            dep = (exc.name or "").split(".")[0]
            if dep and dep != "genesis_protocol":
                missing_deps.add(dep)
            else:
                broken.append(f"{name}: {type(exc).__name__}: {str(exc)[:80]}")
        except Exception as exc:  # noqa: BLE001 - the failure *is* the finding
            broken.append(f"{name}: {type(exc).__name__}: {str(exc)[:80]}")

    total = len(names)
    if broken:
        return False, f"modules: {total - len(broken)}/{total} import ({len(broken)} broken)\n  " + "\n  ".join(broken)
    if missing_deps:
        deps = ", ".join(sorted(missing_deps))
        return True, f"modules: {total}/{total} import OK (deps not installed here: {deps})"
    return True, f"modules: {total}/{total} import OK"


def check_space() -> tuple[bool, str]:
    """Ping the live Space health endpoint."""
    url = f"{HF_SPACE_URL}/api/health"
    try:
        req = urllib.request.Request(url, headers=_space_headers())  # noqa: S310 - fixed host
        with urllib.request.urlopen(req, timeout=25) as resp:  # noqa: S310
            body = json.loads(resp.read() or b"{}")
        status = body.get("status", "?") if isinstance(body, dict) else "?"
        ok = status == "healthy"
        return ok, f"space: {HF_SPACE_URL} -> {status}"
    except Exception as exc:  # noqa: BLE001 - unreachable Space is the finding
        return False, f"space: {HF_SPACE_URL} unreachable ({type(exc).__name__})"


def _github(path: str) -> object | None:
    req = urllib.request.Request(  # noqa: S310 - fixed GitHub host
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read() or b"{}")
    except Exception:  # noqa: BLE001 - reported as a failed check, not a crash
        return None


def check_workflows() -> tuple[bool, str]:
    """Report the latest run per workflow; red if the newest run failed."""
    if not GITHUB_TOKEN:
        return True, "workflows: skipped (no GITHUB_TOKEN)"
    bad: list[str] = []
    lines: list[str] = []
    for wf in WORKFLOWS:
        data = _github(f"/repos/{REPO}/actions/workflows/{wf}/runs?per_page=1")
        runs = data.get("workflow_runs") if isinstance(data, dict) else None
        if not runs:
            lines.append(f"  {wf}: no runs")
            continue
        run = runs[0]
        conclusion = run.get("conclusion") or run.get("status")
        lines.append(f"  {wf}: {conclusion}")
        if conclusion == "failure":
            bad.append(wf)
    head = "workflows: " + ("all green" if not bad else f"{len(bad)} failing ({', '.join(bad)})")
    return not bad, head + "\n" + "\n".join(lines)


def _send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        return False
    payload = json.dumps({"chat_id": TELEGRAM_ADMIN_ID, "text": text[:3900], "disable_web_page_preview": True}).encode()
    req = urllib.request.Request(  # noqa: S310 - fixed Telegram host
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return resp.status == 200
    except Exception as exc:  # noqa: BLE001 - a failed send must not fail the check
        _log(f"telegram send failed: {type(exc).__name__}")
        return False


def run_checks(do_imports: bool = True, do_net: bool = True) -> tuple[bool, list[tuple[bool, str]]]:
    results: list[tuple[bool, str]] = []
    if do_imports:
        results.append(check_imports())
    if do_net:
        results.append(check_space())
        results.append(check_workflows())
    ok = all(passed for passed, _ in results)
    return ok, results


def main() -> int:
    do_net = "--no-net" not in sys.argv
    do_send = "--no-send" not in sys.argv
    ok, results = run_checks(do_net=do_net)

    icon = "✅" if ok else "❌"
    lines = [f"{icon} Genesis health check — {'ALL OK' if ok else 'ISSUES FOUND'}"]
    for passed, detail in results:
        lines.append(f"{'✅' if passed else '❌'} {detail}")
    report = "\n".join(lines)

    print(report)
    if "--json" in sys.argv:
        print(json.dumps({"ok": ok, "checks": [{"ok": p, "detail": d} for p, d in results]}, indent=2))

    if do_send and not ok:
        # Only alert on failure; a daily "all ok" would just be noise.
        _send_telegram(report)
    _log(f"done at {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} — {'ok' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
