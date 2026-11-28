"""Signed commits must be provable, and signing must never leak the key.

The ruleset requires a verified signature on the default branch. This suite
pins the four properties that make that survivable across recreated sandboxes:

1. the fingerprint the owner compares is computed, not asserted;
2. the automation can never sign the default branch;
3. a signature verdict that cannot be read is a refusal, not a pass;
4. nothing here reads, prints or stores a private key.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from genesis_protocol.security.commit_signing import (
    SIGNING_KEY_SECRET,
    InvalidPublicKeyError,
    SigningError,
    branch_is_signable,
    fingerprint_public_key,
    public_keys_match,
    readiness,
    sign_plan,
    verify_branch,
    workflow_ref_is_trusted,
)

REPO_ROOT = Path(__file__).parent.parent

# A published example key. Its fingerprint is the one GitHub itself shows for it.
KNOWN_KEY = ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl "
             "example@genesis")
KNOWN_FINGERPRINT = "SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU"


def _verified(sha):
    return {"commit": {"verification": {"verified": True, "reason": "valid",
                                        "signature": "-----BEGIN SSH SIGNATURE-----",
                                        "verified_at": "2026-11-24T00:00:00Z"}}}


def _unsigned(sha):
    return {"commit": {"verification": {"verified": False, "reason": "unsigned"}}}


def _http_from(mapping):
    calls = []

    def http(method, url, body):
        calls.append(url)
        for sha, payload in mapping.items():
            if sha in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise AssertionError(f"unexpected url {url}")

    http.calls = calls
    return http


# --- fingerprint -----------------------------------------------------------

def test_fingerprint_matches_the_value_github_shows():
    assert fingerprint_public_key(KNOWN_KEY).fingerprint == KNOWN_FINGERPRINT


def test_fingerprint_ignores_the_comment():
    without = " ".join(KNOWN_KEY.split()[:2])
    assert fingerprint_public_key(without).fingerprint == KNOWN_FINGERPRINT


def test_a_private_key_is_not_accepted_as_a_public_key():
    with pytest.raises(InvalidPublicKeyError):
        fingerprint_public_key("-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n-----END-----")


def test_garbage_is_rejected_not_guessed():
    for text in ("", "ssh-ed25519", "nonsense AAAA", "ssh-ed25519 !!!notbase64!!!"):
        with pytest.raises(InvalidPublicKeyError):
            fingerprint_public_key(text)


def test_keys_match_by_fingerprint_not_by_text():
    other_comment = KNOWN_KEY.replace("example@genesis", "owner@laptop")
    assert public_keys_match(KNOWN_KEY, other_comment) is True
    different = ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB1cJ0F0Q0e6j7Z9t1k9pQ8m0v3s0"
                 "W7k1y6b0m2n4o8P owner@laptop")
    assert public_keys_match(KNOWN_KEY, different) is False


# --- branch and workflow guards -------------------------------------------

@pytest.mark.parametrize("branch", ["main", "master", "refs/heads/main", "refs/heads/master", ""])
def test_the_default_branch_is_never_signable(branch):
    ok, reason = branch_is_signable(branch)
    assert ok is False
    assert "default branch" in reason or "no branch" in reason


@pytest.mark.parametrize("branch", ["feat/x", "agent/y", "fix/z", "sec/a", "refs/heads/feat/w"])
def test_work_branches_are_signable(branch):
    assert branch_is_signable(branch) == (True, "signable")


@pytest.mark.parametrize("branch", ["random", "feature/x", "release/1"])
def test_unexpected_branch_shapes_are_refused(branch):
    ok, reason = branch_is_signable(branch)
    assert ok is False
    assert "signable prefixes" in reason


def test_sign_plan_refuses_main():
    with pytest.raises(SigningError):
        sign_plan("main")


def test_sign_plan_captures_the_message_before_the_reset():
    plan = sign_plan("feat/x", mode="squash-sign")
    rewrite = plan["rewrite"]
    message_at = next(i for i, c in enumerate(rewrite) if "--format='%B'" in c)
    reset_at = next(i for i, c in enumerate(rewrite) if "reset --soft" in c)
    assert message_at < reset_at, "a reset moves the pointer, so read the message first"
    assert any("--author=" in c for c in rewrite)
    assert any("commit -S" in c for c in rewrite)


def test_sign_plan_never_pushes_plainly():
    plan = sign_plan("feat/x")
    assert "--force-with-lease" in plan["push"]
    assert "main:" not in plan["push"]


def test_resign_needs_a_single_commit():
    with pytest.raises(SigningError):
        sign_plan("feat/x", mode="resign", commits=3)
    assert sign_plan("feat/x", mode="resign", commits=1)["rewrite"] == [
        "git commit --amend --no-edit -S"]


def test_unknown_mode_is_refused():
    with pytest.raises(SigningError):
        sign_plan("feat/x", mode="rewrite-history")


def test_the_workflow_must_be_the_default_branch_copy():
    repo = "owner/repo"
    good = f"{repo}/.github/workflows/sign-branch.yml@refs/heads/main"
    assert workflow_ref_is_trusted(good, repo) == (True, "trusted")

    branch_copy = f"{repo}/.github/workflows/sign-branch.yml@refs/heads/feat/x"
    ok, reason = workflow_ref_is_trusted(branch_copy, repo)
    assert ok is False and "default branch" in reason

    other_repo = "evil/fork/.github/workflows/sign-branch.yml@refs/heads/main"
    ok, reason = workflow_ref_is_trusted(other_repo, repo)
    assert ok is False

    assert workflow_ref_is_trusted("", repo)[0] is False


# --- readiness (no secret may escape) -------------------------------------

def test_readiness_reports_missing_keygen_and_key():
    report = readiness(env={}, which=lambda _: None, exists=lambda _: False)
    assert report["ssh_keygen"] is False
    assert report["private_key_present"] is False
    assert report["can_sign_locally"] is False


def test_readiness_reports_a_usable_key():
    report = readiness(env={"GENESIS_SIGNING_KEY_PATH": "/k"}, which=lambda _: "/usr/bin/ssh-keygen",
                       exists=lambda path: path == "/k")
    assert report["can_sign_locally"] is True


def test_readiness_never_echoes_the_secret_value():
    secret = "-----BEGIN OPENSSH PRIVATE KEY-----do-not-print"
    report = readiness(env={SIGNING_KEY_SECRET: secret}, which=lambda _: None,
                       exists=lambda _: False)
    assert report["secret_in_environment"] is True
    assert secret not in json.dumps(report)
    assert "PRIVATE KEY" not in json.dumps(report)


# --- verification is fail-closed -----------------------------------------

def test_a_signed_commit_passes():
    result = verify_branch("o/r", ["a" * 40], _http_from({"a" * 40: _verified("a" * 40)}))
    assert result["ok"] is True
    assert result["blockers"] == []


def test_an_unsigned_commit_is_a_blocker():
    sha = "b" * 40
    result = verify_branch("o/r", [sha], _http_from({sha: _unsigned(sha)}))
    assert result["ok"] is False
    assert "not signed" in result["blockers"][0]


def test_one_unsigned_commit_among_many_still_blocks():
    good, bad = "c" * 40, "d" * 40
    result = verify_branch("o/r", [good, bad],
                           _http_from({good: _verified(good), bad: _unsigned(bad)}))
    assert result["ok"] is False
    assert len(result["blockers"]) == 1


def test_an_unreadable_verdict_is_a_refusal_not_a_pass():
    sha = "e" * 40
    result = verify_branch("o/r", [sha], _http_from({sha: OSError("network down")}))
    assert result["ok"] is False
    assert "unreadable" in result["blockers"][0]


def test_a_malformed_payload_is_a_refusal():
    sha = "f" * 40
    result = verify_branch("o/r", [sha], _http_from({sha: {"commit": {}}}))
    assert result["ok"] is False


# --- packaging and wiring -------------------------------------------------

def test_importing_the_leaf_does_not_pull_in_dotenv():
    code = ("import sys; import genesis_protocol.security.commit_signing; "
            "print('genesis_protocol.config' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", "the security package must stay lazily imported"


def test_the_signing_workflow_is_manual_environment_scoped_and_guarded():
    text = (REPO_ROOT / ".github" / "workflows" / "sign-branch.yml").read_text()
    assert "workflow_dispatch" in text
    assert "environment: signing" in text
    assert "SSH_SIGNING_KEY" in text
    assert "--force-with-lease" in text
    assert "refs/heads/main\"" in text or "refs/heads/main" in text
    # no push/pull_request trigger: this must never run on its own
    assert "\n  push:" not in text
    assert "\n  pull_request:" not in text


def test_the_verifier_workflow_is_read_only():
    text = (REPO_ROOT / ".github" / "workflows" / "verify-signatures.yml").read_text()
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "verify_signed_commits.py verify" in text
