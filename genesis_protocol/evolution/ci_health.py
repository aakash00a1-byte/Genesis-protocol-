"""CI-aware health model for agent pull requests.

The evolution loop used to count open ``agent/`` PRs and nothing else. That
number cannot distinguish a PR whose CI is green from one whose CI never ran at
all, so a handful of permanently blocked PRs could stall every future cycle.

This module turns the raw GitHub payloads into one explicit state per PR, and
derives three decisions from it: may this PR merge, does the owner have to act,
and does it occupy evolution capacity.

Every rule is fail-closed. Absent evidence is never treated as success:
missing check-runs, an empty job list, ``action_required``, a head that moved
after verification, or a base that lags ``main`` all block a merge.

The module is pure: it performs no I/O, so it is fully testable offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Check-run conclusions that count as green. Anything else, including a
# missing conclusion on an unfinished run, is not green.
GREEN_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
# Conclusions that mean the work is finished and failed.
FAILED_CONCLUSIONS = frozenset({"failure", "timed_out", "cancelled", "startup_failure"})
# Run/check states that mean work is still pending.
PENDING_STATES = frozenset({"queued", "in_progress", "waiting", "pending", "requested"})

# GitHub parks a run in this conclusion when a human must approve it before any
# job is created. It is not a failure and emphatically not a success.
ACTION_REQUIRED = "action_required"

READY_FOR_REVIEW = "READY_FOR_REVIEW"
CI_RUNNING = "CI_RUNNING"
CI_FAILED = "CI_FAILED"
ACTION_REQUIRED_STATE = "ACTION_REQUIRED"
NO_CHECKS = "NO_CHECKS"
STALE_BASE = "STALE_BASE"
SECURITY_BLOCKED = "SECURITY_BLOCKED"
OWNER_ACTION_REQUIRED = "OWNER_ACTION_REQUIRED"

ALL_STATES = (
    READY_FOR_REVIEW,
    CI_RUNNING,
    CI_FAILED,
    ACTION_REQUIRED_STATE,
    NO_CHECKS,
    STALE_BASE,
    SECURITY_BLOCKED,
    OWNER_ACTION_REQUIRED,
)

# States where the PR is genuinely in flight and should consume a capacity slot.
IN_FLIGHT_STATES = frozenset({READY_FOR_REVIEW, CI_RUNNING})
# States the loop cannot fix by itself; the owner has to intervene.
OWNER_BLOCKED_STATES = frozenset(
    {ACTION_REQUIRED_STATE, NO_CHECKS, STALE_BASE, SECURITY_BLOCKED, OWNER_ACTION_REQUIRED}
)

# The harness records the verified commit in the PR body as
# "landed commit: `sha`". Evidence for any other commit is stale by definition.
EVIDENCE_SHA = re.compile(r"landed commit:\s*`([0-9a-fA-F]{7,40})`")


@dataclass(frozen=True)
class Preflight:
    """Whether an authenticated identity may open an agent PR."""

    ok: bool
    actor: str
    reasons: tuple[str, ...] = ()

    def __bool__(self) -> bool:  # pragma: no cover - trivial
        return self.ok


@dataclass(frozen=True)
class PrHealth:
    """The classified state of one agent pull request."""

    number: int
    branch: str
    head_sha: str
    base_sha: str
    state: str
    reasons: tuple[str, ...] = field(default=())
    run_ids: tuple[int, ...] = field(default=())
    check_names: tuple[str, ...] = field(default=())

    @property
    def mergeable(self) -> bool:
        return self.state == READY_FOR_REVIEW

    @property
    def needs_owner(self) -> bool:
        return self.state in OWNER_BLOCKED_STATES

    @property
    def consumes_capacity(self) -> bool:
        return self.state in IN_FLIGHT_STATES

    @property
    def is_green(self) -> bool:
        """True only when CI actually ran and every check passed."""
        return self.state == READY_FOR_REVIEW


def evidence_sha(body: str | None) -> str | None:
    """The commit SHA a PR body claims was verified, or None."""
    match = EVIDENCE_SHA.search(body or "")
    return match.group(1) if match else None


def evidence_matches(head_sha: str, body: str | None) -> bool:
    """True when the recorded evidence is bound to exactly this head.

    A short SHA is accepted when it is a prefix of the head, which is how the
    harness writes it. An absent or different SHA never matches.
    """
    recorded = evidence_sha(body)
    if not recorded or not head_sha:
        return False
    head = head_sha.lower()
    rec = recorded.lower()
    return head.startswith(rec) or rec.startswith(head)


def _check_conclusions(check_runs: list[dict] | None) -> tuple[list[str], list[str]]:
    """Split check-runs into (names, conclusions)."""
    names: list[str] = []
    conclusions: list[str] = []
    for run in check_runs or []:
        names.append(str(run.get("name", "?")))
        # An unfinished check has no conclusion; keep that distinct from green.
        conclusions.append(str(run.get("conclusion") or run.get("status") or "").lower())
    return names, conclusions


def classify_pr(
    *,
    number: int,
    branch: str,
    head_sha: str,
    base_sha: str,
    main_sha: str | None = None,
    body: str | None = None,
    check_runs: list[dict] | None = None,
    runs: list[dict] | None = None,
    require_evidence: bool = True,
) -> PrHealth:
    """Classify one agent PR into exactly one state.

    Precedence is deliberate: a security problem outranks a CI problem, and any
    owner-only blocker outranks a merely failing build, because only the owner
    can clear it.
    """
    names, conclusions = _check_conclusions(check_runs)
    run_list = runs or []
    run_conclusions = [str(r.get("conclusion") or r.get("status") or "").lower() for r in run_list]
    run_ids = tuple(int(r["id"]) for r in run_list if str(r.get("id", "")).isdigit())
    reasons: list[str] = []

    def result(state: str, *why: str) -> PrHealth:
        return PrHealth(
            number=number,
            branch=branch,
            head_sha=head_sha,
            base_sha=base_sha,
            state=state,
            reasons=tuple(reasons) + tuple(why),
            run_ids=run_ids,
            check_names=tuple(names),
        )

    # 1. Evidence bound to the wrong commit invalidates the verification.
    if require_evidence and not evidence_matches(head_sha, body):
        recorded = evidence_sha(body)
        if recorded:
            reasons.append(f"evidence bound to {recorded[:12]}, head is {head_sha[:12]}")
        else:
            reasons.append("PR body carries no verification evidence")
        return result(SECURITY_BLOCKED)

    # 2. A run parked for human approval never executed a single job.
    if ACTION_REQUIRED in run_conclusions:
        reasons.append(
            "GitHub held the run for approval (action_required): 0 jobs ran, "
            "so no check-run exists and CI cannot be green"
        )
        return result(ACTION_REQUIRED_STATE)

    # 3. Nothing reported at all is not success.
    if not conclusions and not run_conclusions:
        reasons.append("no check-runs and no workflow runs reported for the head commit")
        return result(NO_CHECKS)

    # 4. Still running: wait rather than merge or fail.
    if any(c in PENDING_STATES for c in conclusions) or any(
        c in PENDING_STATES for c in run_conclusions
    ):
        reasons.append("CI still running")
        return result(CI_RUNNING)

    # 5. A finished failure blocks.
    failed = [
        name
        for name, conclusion in zip(names, conclusions, strict=False)
        if conclusion in FAILED_CONCLUSIONS
    ]
    if failed or any(c in FAILED_CONCLUSIONS for c in run_conclusions):
        reasons.append("failing checks: " + ", ".join(sorted(set(failed))) if failed else "workflow run failed")
        return result(CI_FAILED)

    # 6. An unknown conclusion is not green. This is the catch-all that keeps a
    #    new GitHub conclusion from silently passing the gate.
    unknown = [
        name
        for name, conclusion in zip(names, conclusions, strict=False)
        if conclusion not in GREEN_CONCLUSIONS
    ]
    if unknown:
        reasons.append("non-green checks: " + ", ".join(sorted(set(unknown))))
        return result(CI_FAILED)

    # 7. Green, but built on a base that has since moved.
    if main_sha and base_sha and base_sha != main_sha:
        reasons.append(f"base {base_sha[:12]} is behind main {main_sha[:12]}")
        return result(STALE_BASE)

    return result(READY_FOR_REVIEW)


def preflight_identity(
    actor: str,
    *,
    repo: str | None = None,
    expected_repo: str | None = None,
    permissions: dict[str, bool] | None = None,
    required_permissions: tuple[str, ...] = (),
) -> Preflight:
    """Check that the authenticated identity can open an agent PR with live CI.

    A push made with the workflow's own ``GITHUB_TOKEN`` is attributed to
    ``github-actions[bot]``. GitHub then holds the resulting ``pull_request``
    run for approval, so the PR can never show green CI. Opening a PR with that
    identity is therefore refused up front, with the reason spelled out, rather
    than producing another permanently blocked PR.
    """
    reasons: list[str] = []
    name = (actor or "").strip()

    if not name:
        reasons.append("no authenticated actor could be determined")
    elif name.endswith("[bot]"):
        reasons.append(
            f"actor '{name}' is a bot identity: GitHub parks its pull_request runs "
            "at action_required with 0 jobs, so the PR's CI can never run"
        )

    if expected_repo and repo and repo != expected_repo:
        reasons.append(f"authenticated against {repo}, expected {expected_repo}")

    for permission in required_permissions:
        if not (permissions or {}).get(permission):
            reasons.append(f"token lacks required permission: {permission}")

    return Preflight(ok=not reasons, actor=name, reasons=tuple(reasons))


@dataclass(frozen=True)
class Capacity:
    """How much evolution work may start, split by what is actually blocking."""

    in_flight: tuple[int, ...]
    owner_blocked: tuple[int, ...]
    max_in_flight: int
    max_owner_blocked: int

    @property
    def may_start(self) -> bool:
        """True only when neither bucket is full."""
        return (
            len(self.in_flight) < self.max_in_flight
            and len(self.owner_blocked) < self.max_owner_blocked
        )

    @property
    def blocked_by(self) -> str:
        if len(self.in_flight) >= self.max_in_flight:
            return f"{len(self.in_flight)} PRs in flight (limit {self.max_in_flight})"
        if len(self.owner_blocked) >= self.max_owner_blocked:
            return (
                f"{len(self.owner_blocked)} PRs need owner action "
                f"(limit {self.max_owner_blocked})"
            )
        return ""


def plan_capacity(
    healths: list[PrHealth],
    *,
    max_in_flight: int = 5,
    max_owner_blocked: int = 5,
) -> Capacity:
    """Split open PRs into in-flight and owner-blocked buckets.

    Counting every open PR equally is what deadlocked the loop: four PRs that
    can never merge held all five slots forever. Separating the buckets lets a
    genuinely broken PR stop consuming capacity, while a second cap keeps the
    loop from quietly piling up unbounded blocked work.
    """
    in_flight = tuple(sorted(h.number for h in healths if h.consumes_capacity))
    owner_blocked = tuple(sorted(h.number for h in healths if h.needs_owner))
    return Capacity(
        in_flight=in_flight,
        owner_blocked=owner_blocked,
        max_in_flight=max_in_flight,
        max_owner_blocked=max_owner_blocked,
    )


def recovery_plan(health: PrHealth) -> tuple[str, ...]:
    """Bounded, non-destructive next steps for a blocked PR.

    These are suggestions for the owner. Nothing here closes a PR, rewrites
    history, or touches a protected file on its own.
    """
    if health.state == ACTION_REQUIRED_STATE:
        return (
            "Owner: approve the held workflow run, or re-push the branch with an "
            "identity whose pull_request runs are not held (AGENT_GH_TOKEN).",
            "Do not merge: no job has run, so the code is unverified.",
        )
    if health.state == NO_CHECKS:
        return (
            "Confirm ci.yml still triggers on pull_request and that the branch "
            "touches a path the workflow watches.",
            "Re-push a new commit to re-trigger CI; an empty job list is not green.",
        )
    if health.state == CI_FAILED:
        return (
            "Read the failing job log and fix the cause on the branch.",
            "Re-run verification after the fix; do not reuse the old evidence.",
        )
    if health.state == STALE_BASE:
        return (
            "Rebase the branch onto current main, then re-run verification so the "
            "evidence names the new head.",
            "A green result from an old base is not evidence for the new one.",
        )
    if health.state == SECURITY_BLOCKED:
        return (
            "Re-run the acceptance gate against the current head and rewrite the "
            "PR body with the resulting evidence.",
            "Never edit the evidence SHA by hand to match a head you did not verify.",
        )
    if health.state == OWNER_ACTION_REQUIRED:
        return ("Owner decision required; the loop will not act on this PR.",)
    return ()


def notification(health: PrHealth, *, repo: str | None = None) -> str:
    """A truthful one-message status line for the owner.

    Only READY_FOR_REVIEW may read as a success, and even that says the PR
    awaits review rather than claiming it shipped. Every message carries the PR
    number and the exact commit it describes.
    """
    head = health.head_sha[:12] or "unknown"
    link = f"PR #{health.number}"
    if repo:
        link = f"{link} (https://github.com/{repo}/pull/{health.number})"
    if health.state == READY_FOR_REVIEW:
        head_line = f"✅ CI green, awaiting review: {link} @ {head}"
    elif health.state == CI_RUNNING:
        head_line = f"⏳ CI running: {link} @ {head}"
    elif health.state == CI_FAILED:
        head_line = f"❌ CI failed: {link} @ {head}"
    elif health.state == ACTION_REQUIRED_STATE:
        head_line = f"🔒 CI blocked, owner approval needed: {link} @ {head}"
    elif health.state == NO_CHECKS:
        head_line = f"⚠️ No CI reported: {link} @ {head}"
    elif health.state == STALE_BASE:
        head_line = f"🔀 Stale base, rebase needed: {link} @ {head}"
    elif health.state == SECURITY_BLOCKED:
        head_line = f"🛡️ Verification evidence mismatch: {link} @ {head}"
    else:
        head_line = f"🙋 Owner action required: {link} @ {head}"
    detail = "; ".join(health.reasons)
    return f"{head_line}\n{detail}" if detail else head_line


def _fetch_health(repo: str, token: str) -> list[PrHealth]:
    """Read live state for every open agent PR. Network lives only here."""
    import json
    import urllib.request

    def api(path: str):
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repo}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")

    main_sha = api("/git/ref/heads/main")["object"]["sha"]
    pulls = [p for p in api("/pulls?state=open&per_page=100") if isinstance(p, dict)]
    healths: list[PrHealth] = []
    for pull in pulls:
        if not str(pull.get("head", {}).get("ref", "")).startswith("agent/"):
            continue
        sha = pull["head"]["sha"]
        checks = api(f"/commits/{sha}/check-runs").get("check_runs", [])
        runs = api(f"/actions/runs?head_sha={sha}&per_page=100").get("workflow_runs", [])
        healths.append(
            classify_pr(
                number=int(pull["number"]),
                branch=pull["head"]["ref"],
                head_sha=sha,
                base_sha=pull["base"]["sha"],
                main_sha=main_sha,
                body=pull.get("body"),
                check_runs=checks,
                runs=runs,
            )
        )
    return healths


def main(argv: list[str] | None = None) -> int:
    """Print a truthful CI report for open agent PRs, then the capacity verdict.

    Read-only: this never approves, merges, closes or pushes anything.
    """
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Report CI health of open agent PRs.")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--max-in-flight", type=int, default=5)
    parser.add_argument("--max-owner-blocked", type=int, default=5)
    args = parser.parse_args(argv)

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("GITHUB_TOKEN is not set; cannot read PR state.")
        return 2

    healths = _fetch_health(args.repo, token)
    if not healths:
        print("No open agent PRs.")
        return 0
    for health in healths:
        print(notification(health, repo=args.repo))
        for step in recovery_plan(health):
            print(f"    -> {step}")
        print()

    capacity = plan_capacity(
        healths,
        max_in_flight=args.max_in_flight,
        max_owner_blocked=args.max_owner_blocked,
    )
    print(f"in flight     : {capacity.in_flight}")
    print(f"owner blocked : {capacity.owner_blocked}")
    print(f"may start     : {capacity.may_start} ({capacity.blocked_by or 'clear'})")
    return 0 if capacity.may_start else 1


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())

