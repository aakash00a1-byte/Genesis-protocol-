#!/usr/bin/env python3
"""Probe: does a ``pull_request``-only ruleset block direct pushes and allow merges?

Item 2 of the V7 security recovery order asks for the proposed protection to be
tested on a *disposable* branch before anyone touches ``main``. This script is
that test. It never reads or writes ``main``: every object it creates lives under
``refs/heads/probe-*`` and is removed again.

What it does (only with ``--apply``):

1. creates the branch ``probe-base`` from ``main`` *before* the ruleset exists;
2. creates a temporary ruleset named ``pr-only-probe`` scoped to
   ``refs/heads/probe-*`` carrying only the ``pull_request`` rule, with no
   bypass actors -- the configuration under test;
3. commits on ``probe-base`` and pushes directly  -> expected: **rejected**;
4. opens a pull request ``probe-pr`` -> ``probe-base`` and merges it
   -> expected: **accepted**;
5. deletes the pull request, both branches and the ruleset.

Default is ``--dry-run``: it prints the plan and the current ruleset inventory
and touches nothing. Creating a ruleset needs owner approval, so the apply path
is explicit.

Usage::

    python3 scripts/probe_pr_only_ruleset.py                # dry run
    GITHUB_TOKEN=... python3 scripts/probe_pr_only_ruleset.py --apply
    GITHUB_TOKEN=... python3 scripts/probe_pr_only_ruleset.py --apply --keep

Requires a token with ``contents: write`` and ``administration: write`` on the
repository. Nothing is printed from the token.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
RULESET_NAME = "pr-only-probe"
BRANCH_GLOB = "refs/heads/probe-*"
BASE_BRANCH = "probe-base"
PR_BRANCH = "probe-pr"


def _call(method: str, url: str, token: str, payload: dict | None = None) -> object:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed GitHub host
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            body = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
    return json.loads(body or b"{}")


def _git(args: list[str], cwd: str, token: str, repo: str) -> tuple[int, str]:
    """Run git with an authenticated URL substituted for ``{url}``.

    The token only ever exists inside the argv we build here; it is redacted
    from everything this function returns.
    """
    url = f"https://x-access-token:{token}@github.com/{repo}.git"
    cmd = ["git", "-c", "credential.helper=", *[url if a == "{url}" else a for a in args]]
    out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=180)
    text = (out.stdout + out.stderr).replace(token, "<redacted>")
    return out.returncode, text


def _proposed_ruleset() -> dict:
    return {
        "name": RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": [BRANCH_GLOB], "exclude": []}},
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                },
            }
        ],
    }


def _existing_probe_rulesets(repo: str, token: str) -> list[dict]:
    rulesets = _call("GET", f"{API}/repos/{repo}/rulesets", token)
    if not isinstance(rulesets, list):
        return []
    found = []
    for summary in rulesets:
        if summary.get("name") == RULESET_NAME:
            detail = _call("GET", f"{API}/repos/{repo}/rulesets/{summary['id']}", token)
            found.append(detail if isinstance(detail, dict) else summary)
    return found


def _cleanup(repo: str, token: str, ruleset_id: int | None, pr_number: int | None) -> None:
    if pr_number:
        try:
            _call("PATCH", f"{API}/repos/{repo}/pulls/{pr_number}", token, {"state": "closed"})
            print("  closed probe pull request")
        except RuntimeError as exc:
            print(f"  ! could not close PR: {exc}")
    for branch in (BASE_BRANCH, PR_BRANCH):
        try:
            _call("DELETE", f"{API}/repos/{repo}/git/refs/heads/{branch}", token)
            print(f"  deleted branch {branch}")
        except RuntimeError as exc:
            print(f"  ! could not delete {branch}: {exc}")
    if ruleset_id:
        try:
            _call("DELETE", f"{API}/repos/{repo}/rulesets/{ruleset_id}", token)
            print(f"  deleted ruleset {ruleset_id}")
        except RuntimeError as exc:
            print(f"  ! could not delete ruleset {ruleset_id}: {exc}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--apply", action="store_true", help="actually create/merge/delete")
    parser.add_argument("--keep", action="store_true", help="skip cleanup (inspect by hand)")
    parser.add_argument("--workdir", default="/tmp/pr-only-probe")
    args = parser.parse_args(argv)

    if not args.repo:
        parser.error("--repo owner/name (or GITHUB_REPOSITORY) is required")
    token = os.getenv("AGENT_GH_TOKEN") or os.getenv("GITHUB_TOKEN") or ""

    print(f"probe target: {args.repo}")
    print(f"ruleset under test: {json.dumps(_proposed_ruleset(), indent=2)}")

    if not args.apply:
        print("\nDRY RUN - nothing will be created. Planned steps:")
        for step in (
            f"1. create branch {BASE_BRANCH} from main (before the ruleset exists)",
            f"2. create ruleset {RULESET_NAME!r} scoped to {BRANCH_GLOB}",
            "3. push a commit directly to probe-base      -> expect REJECTED",
            f"4. open {PR_BRANCH} -> {BASE_BRANCH} PR and merge -> expect ACCEPTED",
            "5. delete the PR, both branches and the ruleset",
        ):
            print(f"   {step}")
        return 0

    if not token:
        print("error: set AGENT_GH_TOKEN or GITHUB_TOKEN", file=sys.stderr)
        return 2

    existing = _existing_probe_rulesets(args.repo, token)
    if existing:
        print(f"refusing to start: ruleset {RULESET_NAME!r} already exists")
        return 2

    main_sha = _call("GET", f"{API}/repos/{args.repo}/git/ref/heads/main", token)["object"]["sha"]
    _call(
        "POST",
        f"{API}/repos/{args.repo}/git/refs",
        token,
        {"ref": f"refs/heads/{BASE_BRANCH}", "sha": main_sha},
    )
    print(f"created {BASE_BRANCH} at {main_sha[:8]}")

    ruleset = _call("POST", f"{API}/repos/{args.repo}/rulesets", token, _proposed_ruleset())
    ruleset_id = int(ruleset["id"])
    print(f"created ruleset {ruleset_id}")

    pr_number: int | None = None
    try:
        subprocess.run(["rm", "-rf", args.workdir], check=False)
        code, out = _git(
            ["clone", "--depth", "5", "{url}", args.workdir], "/tmp", token, args.repo
        )
        if code != 0:
            print(out)
            return 1
        _git(["checkout", BASE_BRANCH], args.workdir, token, args.repo)

        with open(os.path.join(args.workdir, "probe-direct.txt"), "w") as fh:
            fh.write("direct push probe\n")
        _git(["add", "probe-direct.txt"], args.workdir, token, args.repo)
        _git(
            ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
             "commit", "-m", "probe: direct push"],
            args.workdir, token, args.repo,
        )
        code, out = _git(["push", "{url}", f"HEAD:{BASE_BRANCH}"], args.workdir, token, args.repo)
        direct_rejected = code != 0
        print(f"\n[3] direct push rejected: {direct_rejected}")
        last = out.strip().splitlines()[-1] if out.strip() else "(no output)"
        print(f"    {last}")

        _git(["checkout", "-b", PR_BRANCH], args.workdir, token, args.repo)
        with open(os.path.join(args.workdir, "probe-pr.txt"), "w") as fh:
            fh.write("pull request probe\n")
        _git(["add", "probe-pr.txt"], args.workdir, token, args.repo)
        _git(
            ["-c", "user.name=probe", "-c", "user.email=probe@example.invalid",
             "commit", "-m", "probe: pull request"],
            args.workdir, token, args.repo,
        )
        _git(["push", "{url}", f"HEAD:{PR_BRANCH}"], args.workdir, token, args.repo)

        pr = _call(
            "POST",
            f"{API}/repos/{args.repo}/pulls",
            token,
            {"title": "probe: pr-only ruleset", "head": PR_BRANCH, "base": BASE_BRANCH},
        )
        pr_number = int(pr["number"])
        merged = _call(
            "PUT", f"{API}/repos/{args.repo}/pulls/{pr_number}/merge", token, {"merge_method": "squash"}
        )
        merge_ok = bool(merged.get("merged"))
        print(f"[4] pull request merged: {merge_ok}")

        print("\nRESULT:", "OK" if (direct_rejected and merge_ok) else "UNEXPECTED")
        return 0 if (direct_rejected and merge_ok) else 1
    finally:
        if not args.keep:
            _cleanup(args.repo, token, ruleset_id, pr_number)
        else:
            print(f"kept ruleset {ruleset_id} and probe branches for inspection")


if __name__ == "__main__":
    raise SystemExit(main())
