"""Tests for the independent patch-verification gate.

The gate sits between the OpenHands sandbox and the push. These tests cover the
two things that matter: a patch that should be refused is refused (fail-closed),
and a patch that should be accepted is accepted with its evidence recorded.

They run against a real temporary git repository and the real kernel
``AcceptanceGate`` / ``IndependentVerifier``, so the code path under test is the
one that ships. No network is touched.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from patch_verification import (  # noqa: E402
    check_path_policy,
    create_scratch_worktree,
    parse_patch_paths,
    remove_scratch_worktree,
    verify_patch,
)


def _patch(path: str, body: str = "x = 1") -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"new file mode 100644\nindex 0000000..1111111\n"
        f"--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+{body}\n"
    )


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture()
def repo(tmp_path):
    """A real git repo with one commit on branch ``main``."""
    root = tmp_path / "repo"
    root.mkdir()
    _git("init", "-q", "-b", "main", cwd=str(root))
    _git("config", "user.email", "t@example.com", cwd=str(root))
    _git("config", "user.name", "t", cwd=str(root))
    (root / "README.md").write_text("hello\n")
    _git("add", "-A", cwd=str(root))
    _git("commit", "-qm", "init", cwd=str(root))
    return root


# ------------------------------------------------------------------
# Path policy — pure functions
# ------------------------------------------------------------------
def test_path_policy_flags_protected_paths() -> None:
    for bad in (
        ".github/workflows/ci.yml",
        "scripts/self_improve.py",
        "scripts/patch_verification.py",
        "scripts/hf_deploy.sh",
        "genesis_protocol/updates/github_prs.py",
    ):
        assert check_path_policy([bad]) == [bad], bad


def test_path_policy_allows_ordinary_paths() -> None:
    assert check_path_policy(
        ["genesis_protocol/foo.py", "tests/test_x.py", "README.md"]
    ) == []


def test_parse_patch_paths_reads_the_diff() -> None:
    patch = _patch("genesis_protocol/a.py") + _patch("tests/test_a.py")
    assert parse_patch_paths(patch) == ["genesis_protocol/a.py", "tests/test_a.py"]


# ------------------------------------------------------------------
# Scratch worktree — real git
# ------------------------------------------------------------------
def test_scratch_worktree_is_isolated_and_removable(repo) -> None:
    wt = create_scratch_worktree("main", str(repo))
    try:
        assert (Path(wt) / "README.md").exists()
        assert not (Path(wt) / "brand_new.py").exists()
    finally:
        remove_scratch_worktree(wt, str(repo))
    assert not Path(wt).exists()


# ------------------------------------------------------------------
# Fail-closed: refuse what must not ship
# ------------------------------------------------------------------
def test_empty_patch_is_refused(repo) -> None:
    result = verify_patch("", repo_root=str(repo), base_ref="main", require_tests=False)
    assert result.accepted is False
    assert "empty patch" in result.reasons


def test_patch_touching_protected_path_is_refused(repo) -> None:
    result = verify_patch(
        _patch(".github/workflows/evil.yml"),
        repo_root=str(repo),
        base_ref="main",
        require_tests=False,
    )
    assert result.accepted is False
    assert result.path_violations == [".github/workflows/evil.yml"]


def test_patch_introducing_a_secret_is_refused(repo) -> None:
    secret = "ghp_" + "a" * 36
    result = verify_patch(
        _patch("genesis_protocol/leak.py", f'TOKEN = "{secret}"'),
        repo_root=str(repo),
        base_ref="main",
        require_tests=False,
    )
    assert result.accepted is False
    assert result.secret_findings == ["genesis_protocol/leak.py"]


def test_required_tests_without_a_runner_is_refused(repo) -> None:
    result = verify_patch(
        _patch("genesis_protocol/ok.py"),
        repo_root=str(repo),
        base_ref="main",
        test_command=None,
        require_tests=True,
    )
    assert result.accepted is False


def test_failing_test_is_refused(repo) -> None:
    patch = _patch("tests/test_probe.py", "def test_fails():\n    assert False")
    result = verify_patch(
        patch,
        repo_root=str(repo),
        base_ref="main",
        test_command='python3 -c "raise SystemExit(1)"',
        require_tests=True,
    )
    assert result.accepted is False
    assert result.tests_run is True
    assert result.tests_passed is False


def test_patch_that_does_not_apply_is_refused(repo) -> None:
    bogus = (
        "diff --git a/nope.txt b/nope.txt\n"
        "--- a/nope.txt\n+++ b/nope.txt\n@@ -1 +1 @@\n-was\n+now\n"
    )
    result = verify_patch(
        bogus, repo_root=str(repo), base_ref="main", require_tests=False
    )
    assert result.accepted is False
    assert any("did not apply" in r for r in result.reasons)


# ------------------------------------------------------------------
# Happy path: accept and record evidence
# ------------------------------------------------------------------
def test_clean_patch_with_passing_tests_is_accepted(repo) -> None:
    result = verify_patch(
        _patch("genesis_protocol/new_module.py", "VALUE = 42"),
        repo_root=str(repo),
        base_ref="main",
        test_command='python3 -c "raise SystemExit(0)"',
        require_tests=True,
    )
    assert result.accepted is True, result.reasons
    assert result.tests_run is True and result.tests_passed is True
    assert result.verifier_passed is True
    assert result.changed_paths == ["genesis_protocol/new_module.py"]


def test_evidence_block_records_the_verdict(repo) -> None:
    result = verify_patch(
        _patch("genesis_protocol/new_module.py", "VALUE = 42"),
        repo_root=str(repo),
        base_ref="main",
        test_command='python3 -c "raise SystemExit(0)"',
        require_tests=True,
    )
    block = result.evidence_block()
    assert "Independent verification" in block
    assert result.patch_sha in block
    assert "secret scan: pass" in block
    assert "tests re-run: passed" in block


def test_landed_sha_is_bound_into_the_evidence(repo) -> None:
    result = verify_patch(
        _patch("genesis_protocol/new_module.py", "VALUE = 42"),
        repo_root=str(repo),
        base_ref="main",
        test_command='python3 -c "raise SystemExit(0)"',
        require_tests=True,
    )
    result.landed_sha = "deadbeefcafe"
    assert "landed commit: `deadbeefcafe`" in result.evidence_block()
