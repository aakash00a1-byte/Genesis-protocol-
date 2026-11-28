#!/usr/bin/env python3
"""Verify, fingerprint and plan signed commits. Read-only, stdlib only.

    python3 scripts/verify_signed_commits.py readiness
    python3 scripts/verify_signed_commits.py fingerprint ~/.ssh/genesis_signing.pub
    python3 scripts/verify_signed_commits.py plan --branch feat/x --mode squash-sign
    python3 scripts/verify_signed_commits.py verify --repo owner/repo --branch feat/x
    python3 scripts/verify_signed_commits.py verify --repo owner/repo --sha <sha>

``verify`` reads GitHub's own verdict for each commit (the same source the merge
gate uses) and exits 1 when any commit is unsigned, 2 when the verdict could not
be read. It never accepts "unknown" as "signed".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genesis_protocol.security.commit_signing import (  # noqa: E402
    SIGNING_KEY_SECRET,
    InvalidPublicKeyError,
    SigningError,
    branch_is_signable,
    fingerprint_public_key,
    readiness,
    sign_plan,
    verify_branch,
)

API_ROOT = "https://api.github.com"


def _http(token: str):
    def call(method: str, url: str, body: dict | None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("User-Agent", "genesis-signed-commit-check")
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode() or "{}")
    return call


def _branch_shas(repo: str, branch: str, base: str, http) -> list[str]:
    url = f"{API_ROOT}/repos/{repo}/compare/{base}...{branch}"
    payload = http("GET", url, None)
    return [c["sha"] for c in payload.get("commits", [])]


def cmd_readiness(_args) -> int:
    report = readiness()
    print(json.dumps(report, indent=2))
    print(f"\nsecret name (never its value): {SIGNING_KEY_SECRET}")
    return 0 if report["can_sign_locally"] or report["secret_in_environment"] else 0


def cmd_fingerprint(args) -> int:
    text = args.key
    if os.path.exists(text):
        text = Path(text).read_text()
    try:
        print(json.dumps(fingerprint_public_key(text).to_dict(), indent=2))
    except InvalidPublicKeyError as exc:
        print(f"not a public key: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_plan(args) -> int:
    try:
        plan = sign_plan(args.branch, mode=args.mode, base=args.base, commits=args.commits)
    except SigningError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2))
    return 0


def cmd_verify(args) -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        print("GITHUB_TOKEN is required to read verification verdicts", file=sys.stderr)
        return 2
    http = _http(token)
    try:
        shas = [args.sha] if args.sha else _branch_shas(args.repo, args.branch, args.base, http)
    except (urllib.error.URLError, KeyError, ValueError) as exc:
        print(f"could not list commits: {exc}", file=sys.stderr)
        return 2
    if not shas:
        print("no commits to check", file=sys.stderr)
        return 2
    result = verify_branch(args.repo, shas, http)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        print(f"RESULT: BLOCKED - {len(result['blockers'])} unsigned commit(s)", file=sys.stderr)
        return 1
    print(f"RESULT: OK - {result['checked']} commit(s) verified")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("readiness", help="what this environment can do").set_defaults(func=cmd_readiness)

    fp = sub.add_parser("fingerprint", help="SHA256 fingerprint of a public key")
    fp.add_argument("key", help="path to a .pub file, or the key itself")
    fp.set_defaults(func=cmd_fingerprint)

    plan = sub.add_parser("plan", help="print the signing commands (executes nothing)")
    plan.add_argument("--branch", required=True)
    plan.add_argument("--mode", default="squash-sign", choices=["squash-sign", "resign"])
    plan.add_argument("--base", default="main")
    plan.add_argument("--commits", type=int, default=1)
    plan.set_defaults(func=cmd_plan)

    verify = sub.add_parser("verify", help="check GitHub's verdict for commits")
    verify.add_argument("--repo", required=True, help="owner/repo")
    verify.add_argument("--branch")
    verify.add_argument("--base", default="main")
    verify.add_argument("--sha")
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    if args.command == "verify" and not (args.branch or args.sha):
        parser.error("verify needs --branch or --sha")
    if args.command == "plan":
        ok, reason = branch_is_signable(args.branch)
        if not ok:
            print(f"refused: {reason}", file=sys.stderr)
            return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
