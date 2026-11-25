"""Commit signature verification for verified landing (V7 P9 extension).

The merge gate refuses a head whose check-runs are not green and whose body
carries no evidence record, but it never asks whether the commits are *signed*.
So if the ``required_signatures`` ruleset were relaxed, an unsigned head could
merge through the gate unnoticed.

This module is that missing primitive: it reads GitHub's own verification
verdict for a commit and returns a refusal reason when the commit is not signed.

Two properties matter and are enforced here:

* **Read-only.** It only issues ``GET`` requests; it has no landing, merge or
  deploy path.
* **Fail-closed.** An unreadable or malformed verdict is reported as *not
  signed*. A network failure must never be mistaken for a valid signature.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

API_ROOT = "https://api.github.com"

HttpFn = Callable[[str, str, dict | None], Any]


@dataclass(frozen=True)
class CommitSignature:
    """GitHub's verification verdict for one commit."""

    sha: str
    verified: bool
    reason: str
    signature_type: str | None = None
    author: str | None = None
    committer: str | None = None

    def refusal(self) -> str | None:
        """Why this commit must not be merged, or ``None`` when it is signed."""
        if self.verified:
            return None
        return f"commit {self.sha[:12]} is not signed (reason: {self.reason or 'unknown'})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "sha": self.sha,
            "verified": self.verified,
            "reason": self.reason,
            "signature_type": self.signature_type,
            "author": self.author,
            "committer": self.committer,
        }


def commit_url(repo: str, sha: str) -> str:
    return f"{API_ROOT}/repos/{repo}/commits/{sha}"


def read_signature(repo: str, sha: str, http: HttpFn) -> CommitSignature:
    """Read one commit's verification verdict. Never raises; fails closed."""
    try:
        payload = http("GET", commit_url(repo, sha), None)
    except Exception as exc:  # noqa: BLE001 - a gate must not depend on the network
        return CommitSignature(sha=sha, verified=False, reason=f"unreadable: {type(exc).__name__}")

    if not isinstance(payload, dict):
        return CommitSignature(sha=sha, verified=False, reason="unreadable: bad payload")

    commit = payload.get("commit")
    verification = commit.get("verification") if isinstance(commit, dict) else None
    if not isinstance(verification, dict):
        return CommitSignature(sha=sha, verified=False, reason="unreadable: no verdict")

    verified = verification.get("verified") is True
    # The reason is only meaningful when GitHub actually returned a boolean.
    # A truthy string ("true") or 1 used to reach the refusal message as
    # "not signed (reason: valid)", which reads like a contradiction.
    raw_verdict = verification.get("verified")
    reason = str(verification.get("reason") or "unknown")
    if not verified and raw_verdict is not False:
        reason = f"verdict was {raw_verdict!r}, not a boolean true"
    signature_type = verification.get("signature_type")

    author = payload.get("author")
    committer = payload.get("committer")
    return CommitSignature(
        sha=str(payload.get("sha") or sha),
        verified=verified,
        reason=reason,
        signature_type=str(signature_type) if signature_type else None,
        author=str(author.get("login")) if isinstance(author, dict) else None,
        committer=str(committer.get("login")) if isinstance(committer, dict) else None,
    )


def signature_blockers(repo: str, shas: Iterable[str], http: HttpFn) -> list[str]:
    """Refusal reasons for every unsigned commit. Empty means all signed.

    Every commit in a pull request must be signed, not just the head, so the
    caller passes the full list.
    """
    blockers: list[str] = []
    for sha in shas:
        refusal = read_signature(repo, sha, http).refusal()
        if refusal:
            blockers.append(refusal)
    return blockers
