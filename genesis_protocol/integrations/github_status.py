"""Read-only GitHub connection status for GLUTEN.

Reports whether the bot can reach the Genesis repository and, if so, the open
pull requests. This is deliberately read-only: it never merges, pushes, or
changes anything, so it is safe to expose to the owner from Telegram or the
web interface.

Token resolution prefers the read-only-capable ``GITHUB_TOKEN`` and falls back
to ``AGENT_GH_TOKEN``. The token value is never returned - only whether a
credential is present and what the API answered.

Every failure is reported as a reason, never as an invented success. A caller
can always tell "could not check" apart from "checked and found nothing".
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable

REPO = "aakash00a1-byte/Genesis-protocol-"

HttpFn = Callable[[str], Any]

_TOKEN_ENV_ORDER = ("GITHUB_TOKEN", "AGENT_GH_TOKEN", "OH_GIT_CREDENTIAL_ACCESS_TOKEN_GITHUB")


def _token() -> str:
    for name in _TOKEN_ENV_ORDER:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def token_present() -> bool:
    return bool(_token())


def _default_http(url: str) -> Any:
    request = urllib.request.Request(  # noqa: S310 - fixed api.github.com host
        url,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Genesis-Protocol-GLUTEN",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc


def _reason(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text[:200]


def status(*, http: HttpFn | None = None) -> dict[str, Any]:
    """Return connection status and open PRs, or a reason it is unknown.

    ``http`` is injectable so the caller can test offline. It receives a URL and
    returns decoded JSON.
    """
    if not token_present():
        return {
            "connected": False,
            "repo": REPO,
            "token_present": False,
            "reason": "no GitHub token configured (GITHUB_TOKEN or AGENT_GH_TOKEN)",
        }

    get = http or _default_http

    try:
        repo = get(f"https://api.github.com/repos/{REPO}")
    except Exception as exc:  # noqa: BLE001 - report, never raise into a chat reply
        return {
            "connected": False,
            "repo": REPO,
            "token_present": True,
            "reason": f"repo read failed: {_reason(exc)}",
        }

    if not isinstance(repo, dict):
        return {
            "connected": False,
            "repo": REPO,
            "token_present": True,
            "reason": "unexpected repo response",
        }

    result: dict[str, Any] = {
        "connected": True,
        "repo": repo.get("full_name", REPO),
        "token_present": True,
        "default_branch": repo.get("default_branch"),
        "private": repo.get("private"),
        # Only the booleans, never a token or a scope string.
        "permissions": {
            k: bool(v) for k, v in (repo.get("permissions") or {}).items()
        },
        "pulls": [],
        "pulls_error": None,
    }

    try:
        pulls = get(f"https://api.github.com/repos/{REPO}/pulls?state=open&per_page=50")
        if isinstance(pulls, list):
            result["pulls"] = [
                {
                    "number": p.get("number"),
                    "title": str(p.get("title", "")).strip()[:120],
                    "branch": (p.get("head") or {}).get("ref", ""),
                    "url": p.get("html_url", ""),
                    "draft": bool(p.get("draft")),
                }
                for p in pulls
            ]
    except Exception as exc:  # noqa: BLE001
        result["pulls_error"] = _reason(exc)

    return result


def format_status(data: dict[str, Any]) -> str:
    """Render ``status`` output as a short Telegram-ready message."""
    if not data.get("connected"):
        return f"GitHub: NOT CONNECTED\nRepo: {data.get('repo')}\nReason: {data.get('reason')}"

    lines = [
        "GitHub: CONNECTED",
        f"Repo: {data.get('repo')}",
        f"Default branch: {data.get('default_branch')}",
    ]
    if data.get("pulls_error"):
        lines.append(f"Open PRs: UNKNOWN ({data['pulls_error']})")
    else:
        pulls = data.get("pulls") or []
        lines.append(f"Open PRs: {len(pulls)}")
        for p in pulls[:10]:
            mark = " (draft)" if p.get("draft") else ""
            lines.append(f"  #{p.get('number')} {p.get('title')}{mark}")
    lines.append("Read-only view; nothing here merges or pushes.")
    return "\n".join(lines)
