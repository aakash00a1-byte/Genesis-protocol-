"""GitHub PR transport for the approval gate.

Turns an owner's ``/approve`` into a real merge. The merge is the push: it
lands the agent's branch on ``main``, which triggers ``deploy-space.yml`` and
deploys to the HF Space. ``/reject`` closes the PR instead.

A pull request is the unit of an update: it already carries the branch, the
diff and the review surface, so there is no second store to keep in sync. The
transport is thin and injectable (``http``), so it is fully testable offline.

Requires a token that can merge in this repository. The agent's sandbox token
is read-only; approval must run with the owner's write token, supplied as the
``AGENT_GH_TOKEN`` secret.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from . import Update, resolve

# Only branches the self-improvement harness creates are approvable, so a
# human's own PR cannot be merged by this command by accident.
AGENT_BRANCH_PREFIX = "agent/"

HttpFn = Callable[[str, str, dict | None], Any]


def _default_http(method: str, url: str, payload: dict | None) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed GitHub host
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_TOKEN[0]}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
    return json.loads(body or b"{}")


# The default http needs the token; keep it in a module slot so the callable
# signature stays (method, url, payload).
_TOKEN: list[str] = [""]


class GitHubPRTransport:
    """Approval transport backed by GitHub pull requests."""

    def __init__(
        self,
        repo: str,
        token: str,
        *,
        http: HttpFn | None = None,
        branch_prefix: str = AGENT_BRANCH_PREFIX,
    ) -> None:
        self.repo = repo
        self.token = token
        self.branch_prefix = branch_prefix
        if http is not None:
            self._http = http
        else:
            _TOKEN[0] = token
            self._http = _default_http

    # -- reads ----------------------------------------------------------
    def _pulls(self) -> list[dict]:
        pulls = self._http("GET", f"https://api.github.com/repos/{self.repo}/pulls?state=open&per_page=100", None)
        return pulls if isinstance(pulls, list) else []

    def _to_update(self, pull: dict) -> Update:
        branch = str(pull.get("head", {}).get("ref", ""))
        return Update(
            id=str(pull.get("number", "")),
            title=str(pull.get("title", "")).strip(),
            branch=branch,
            url=str(pull.get("html_url", "")),
            area="",
            priority=0.5,
            state="proposed",
        )

    def list_open(self) -> list[Update]:
        return [
            self._to_update(pull)
            for pull in self._pulls()
            if str(pull.get("head", {}).get("ref", "")).startswith(self.branch_prefix)
        ]

    def _find(self, token: str) -> Update | None:
        return resolve(self.list_open(), token)

    # -- decisions ------------------------------------------------------
    def approve(self, token: str, reason: str = "") -> str:
        item = self._find(token)
        if item is None:
            return f"Update '{token}' nahi mila (ya already decided)."
        payload: dict[str, Any] = {
            "merge_method": "squash",
            "commit_title": f"{item.title} (#{item.id})",
        }
        if reason:
            payload["commit_message"] = reason
        result = self._http(
            "PUT",
            f"https://api.github.com/repos/{self.repo}/pulls/{item.id}/merge",
            payload,
        )
        if isinstance(result, dict) and result.get("merged"):
            return (
                f"✅ Approved & merged: {item.title}\n"
                f"main par push ho gaya; deploy workflow chal raha hai.\n"
                f"sha: {result.get('sha', '-')}"
            )
        message = result.get("message") if isinstance(result, dict) else None
        return f"⚠️ merge fail: {message or 'unknown error'}"

    def reject(self, token: str, reason: str = "") -> str:
        item = self._find(token)
        if item is None:
            return f"Update '{token}' nahi mila (ya already decided)."
        if reason:
            self._http(
                "POST",
                f"https://api.github.com/repos/{self.repo}/issues/{item.id}/comments",
                {"body": f"Rejected: {reason}"},
            )
        self._http(
            "PATCH",
            f"https://api.github.com/repos/{self.repo}/pulls/{item.id}",
            {"state": "closed"},
        )
        return f"❌ Rejected & closed: {item.title}"

    def status(self, token: str) -> str:
        item = self._find(token)
        if item is None:
            return f"Update '{token}' nahi mila."
        return (
            f"#{item.id} — {item.title}\n"
            f"branch: {item.branch or '-'}\n"
            f"url: {item.url or '-'}"
        )
