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
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from . import Update, resolve

# Only branches the self-improvement harness creates are approvable, so a
# human's own PR cannot be merged by this command by accident.
AGENT_BRANCH_PREFIX = "agent/"

# A check-run with one of these conclusions does not block a merge. Anything
# else (failure, cancelled, timed_out, action_required, ...) does.
#
# ``skipped`` and ``neutral`` are deliberately absent. They were here before and
# made this gate fail open: a single skipped check — or a PR that ran only the
# linter — was enough to merge, because no test had to pass. A merge is the push
# to main, so the gate has to be at least as strict as the read-only model in
# ``genesis_protocol.evolution.ci_health``.
_CHECK_RUN_OK = {"success"}

# The evidence SHA the harness recorded in the PR body ("landed commit: `sha`").
_EVIDENCE_SHA = re.compile(r"landed commit:\s*`([0-9a-fA-F]{7,40})`")


def _required_checks() -> frozenset[str]:
    """Job names that must report before a merge. Sourced from the shared model.

    If the model cannot be imported the gate must still be strict, so it falls
    back to the repository's own required set rather than skipping the rule.
    """
    try:
        from genesis_protocol.evolution.ci_health import REQUIRED_CHECKS
    except Exception:  # noqa: BLE001 - a gate must not depend on an import
        return frozenset({"lint", "test"})
    return frozenset(REQUIRED_CHECKS)

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
        on_merged: Callable[[Update], None] | None = None,
        require_checks: bool = True,
        require_signatures: bool = True,
        allow_unverified: bool = False,
    ) -> None:
        self.repo = repo
        self.token = token
        self.branch_prefix = branch_prefix
        self.on_merged = on_merged
        # Refuse to merge unless the head commit's check-runs are green and the
        # PR body carries an evidence record bound to that same commit. On by
        # default: an approval should never be able to ship an unverified head.
        #
        # This is deliberately not configurable in production. It used to be a
        # plain constructor flag, which meant one environment variable in the
        # approval harness (``SELF_IMPROVE_REQUIRE_CHECKS=0``) silently turned
        # off the CI check, the evidence check *and* the signature check. A
        # verification gate that can be switched off by configuration is not a
        # gate, so disabling it now requires ``allow_unverified=True``, which
        # only an isolated test driving a fake transport passes.
        if not require_checks and not allow_unverified:
            raise ValueError(
                "the merge gate cannot be disabled: it verifies CI, the evidence "
                "record and every commit signature. allow_unverified=True exists "
                "only for isolated tests with a fake transport."
            )
        self.require_checks = True if not allow_unverified else require_checks
        # Every commit in the PR must carry a verified signature, not just the
        # head. This is the gate's own check, so it still holds if the
        # ``required_signatures`` ruleset is ever relaxed.
        self.require_signatures = require_signatures
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
            head_sha=str(pull.get("head", {}).get("sha", "")),
            body=str(pull.get("body") or ""),
        )

    def list_open(self) -> list[Update]:
        return [
            self._to_update(pull)
            for pull in self._pulls()
            if str(pull.get("head", {}).get("ref", "")).startswith(self.branch_prefix)
        ]

    def _find(self, token: str) -> Update | None:
        return resolve(self.list_open(), token)

    def _check_runs(self, sha: str) -> list[dict] | None:
        """Check-runs for a commit, or None when the API refuses to read them.

        ``None`` is distinct from ``[]``: the first means we could not ask
        (a token without ``checks: read``, or a network error), the second
        means GitHub answered and reported nothing. Both block a merge, but
        they need different messages, so the caller can tell them apart.

        The check-runs endpoint needs the ``checks: read`` permission, which a
        fine-grained PAT often lacks. When it refuses, fall back to the Actions
        runs API for the same commit: it needs only ``actions: read`` and
        reports each workflow run's conclusion, which is what the gate is
        actually asking about.
        """
        try:
            data = self._http(
                "GET",
                f"https://api.github.com/repos/{self.repo}/commits/{sha}/check-runs",
                None,
            )
        except Exception:  # noqa: BLE001 - try the fallback before giving up
            return self._workflow_runs(sha)
        runs = data.get("check_runs") if isinstance(data, dict) else None
        return runs if isinstance(runs, list) else []

    def _workflow_runs(self, sha: str) -> list[dict] | None:
        """Workflow-run conclusions for a commit, shaped like check-runs.

        The fallback for a token that can read Actions but not Checks. Returns
        None when even this cannot be read, so the caller still fails closed.
        """
        try:
            data = self._http(
                "GET",
                f"https://api.github.com/repos/{self.repo}/actions/runs"
                f"?head_sha={sha}&per_page=100",
                None,
            )
        except Exception:  # noqa: BLE001 - an unreadable gate blocks, it must not crash
            return None
        runs = data.get("workflow_runs") if isinstance(data, dict) else None
        if not isinstance(runs, list):
            return None
        return [
            {
                "name": str(r.get("name", "?")),
                # A run still in progress has no conclusion; treat it as not
                # yet green so the gate waits rather than merging early.
                "conclusion": r.get("conclusion") or r.get("status"),
            }
            for r in runs
        ]

    _COMMITS_PER_PAGE = 100
    # 50 pages = 5000 commits. Past that the list is refused rather than
    # truncated: an unverified tail must never look like a verified whole.
    _COMMITS_MAX_PAGES = 50

    def _commit_shas(self, number: str) -> tuple[list[str] | None, str]:
        """Every commit SHA in the pull request, or ``(None, reason)``.

        All commits matter, not just the head: an unsigned commit buried in the
        middle of a branch still lands on main when the PR is squashed. GitHub
        pages this endpoint, so a single request only ever sees the first 100
        commits -- a one-page implementation would leave commit 101 onward
        unchecked. Every page is therefore read, and anything unreadable or
        malformed fails closed.
        """
        shas: list[str] = []
        page = 1
        while True:
            if page > self._COMMITS_MAX_PAGES:
                limit = self._COMMITS_PER_PAGE * self._COMMITS_MAX_PAGES
                return None, f"more than {limit} commits; refusing a truncated list"
            try:
                payload = self._http(
                    "GET",
                    f"https://api.github.com/repos/{self.repo}/pulls/{number}/commits"
                    f"?per_page={self._COMMITS_PER_PAGE}&page={page}",
                    None,
                )
            except Exception as exc:  # noqa: BLE001 - fail closed below
                return None, f"page {page} unreadable ({type(exc).__name__})"
            if not isinstance(payload, list):
                return None, f"page {page} was not a commit list"
            for entry in payload:
                sha = entry.get("sha") if isinstance(entry, dict) else None
                if not isinstance(sha, str) or not sha.strip():
                    return None, f"page {page} carried a commit without a sha"
                shas.append(sha)
            if len(payload) < self._COMMITS_PER_PAGE:
                return shas, ""
            page += 1

    def _signature_blockers(self, shas: list[str]) -> list[str]:
        """Refusal reasons from ``evolution.signed_commit``; fails closed.

        The import is deferred on purpose: ``genesis_protocol.updates`` must stay
        importable with the standard library alone (the self-improvement runner
        has no third-party packages), and ``genesis_protocol.evolution`` pulls a
        much larger dependency graph at import time.
        """
        try:
            from genesis_protocol.evolution.signed_commit import signature_blockers
        except Exception as exc:  # noqa: BLE001 - a gate must not fail open
            return [
                "signature verification unavailable "
                f"({type(exc).__name__}); refusing to merge"
            ]
        return signature_blockers(self.repo, shas, self._http)

    def _merge_blockers(self, item: Update) -> list[str]:
        """Reasons this approval must not merge. Empty means clear to merge.

        Three independent conditions, all fail-closed: the head commit's
        check-runs must all be green, the PR body must carry an evidence record
        bound to that exact commit, and every commit must be signed. A head that
        moved after verification, an unverified head, or an unsigned commit is
        refused.
        """
        if not self.require_checks:
            return []
        blockers: list[str] = []
        sha = item.head_sha
        if not sha:
            return ["PR head commit could not be read"]

        evidence = _EVIDENCE_SHA.search(item.body or "")
        if evidence is None:
            blockers.append("PR body has no verification evidence")
        else:
            recorded = evidence.group(1)
            if not (sha.startswith(recorded) or recorded.startswith(sha)):
                blockers.append(
                    f"evidence bound to {recorded}, but the head is {sha[:12]}"
                )

        if self.require_signatures:
            commits, why = self._commit_shas(item.id)
            if commits is None:
                blockers.append(
                    "PR commits could not be read — signatures cannot be verified"
                    + (f" ({why})" if why else "")
                )
            elif not commits:
                blockers.append("PR reports no commits to verify")
            else:
                blockers.extend(self._signature_blockers(commits))

        runs = self._check_runs(sha)
        if runs is None:
            blockers.append(
                "check-runs could not be read — the merge token needs "
                "`checks: read` (repo secret AGENT_GH_TOKEN, or the workflow's "
                "permissions block)"
            )
        elif not runs:
            blockers.append("no check-runs reported for the head commit")
        else:
            bad = [
                r for r in runs if str(r.get("conclusion")) not in _CHECK_RUN_OK
            ]
            if bad:
                names = ", ".join(sorted({str(r.get("name", "?")) for r in bad}))
                blockers.append(f"check-runs not green: {names}")
            # A green subset is not a verified PR. Merging on the strength of the
            # linter alone would push untested code to main, so every required
            # job must have reported. The set comes from ci.yml via the shared
            # model, not from a second hardcoded copy.
            missing = _required_checks() - {str(r.get("name", "")) for r in runs}
            if missing:
                blockers.append(
                    "required checks never reported: " + ", ".join(sorted(missing))
                )
        return blockers

    # -- decisions ------------------------------------------------------
    def approve(self, token: str, reason: str = "") -> str:
        item = self._find(token)
        if item is None:
            return f"Update '{token}' nahi mila (ya already decided)."
        blockers = self._merge_blockers(item)
        if blockers:
            return (
                "⚠️ merge blocked — verification gate:\n- "
                + "\n- ".join(blockers)
                + "\n\nCI green hone aur evidence head se match hone ke baad "
                "dobara /approve karein."
            )
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
            if self.on_merged is not None:
                try:
                    self.on_merged(item)
                except Exception:  # noqa: BLE001 - deploy dispatch must not fail the merge reply
                    pass
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
