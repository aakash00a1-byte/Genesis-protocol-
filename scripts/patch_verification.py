#!/usr/bin/env python3
"""Independent verification gate for agent-produced patches.

The self-improvement harness used to take a patch straight out of the OpenHands
sandbox and push it. This module inserts a gate between the sandbox and the
push: the patch is listed for its changed paths, those paths are checked against
a policy, the patch is applied to a throwaway worktree of the base branch, the
changed files are scanned for secrets, the test suite is re-run, and the
kernel's ``IndependentVerifier`` scores the result. Only a patch that passes all
of it is returned as accepted.

The verifier and acceptance gate live in ``genesis_v5`` (package root
``genesis``), which the product never imported. Rather than fork them, this
module loads them from their own tree, so the harness and the kernel share one
implementation.

Fail-closed by construction: a missing git, a worktree that will not build, a
missing verifier, or a failing test all yield ``accepted=False``. Nothing here
writes to the repository, commits, or pushes.
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KERNEL_DIR = os.path.join(_ROOT, "genesis_v5")

# Paths the agent may never touch. These are the controls that would otherwise
# let a patch weaken or bypass its own gate: CI config, the harness, the
# approval transport, and the deploy script.
PROTECTED_PREFIXES = (
    ".github/",
    "scripts/self_improve.py",
    "scripts/patch_verification.py",
    "scripts/hf_deploy.sh",
    "genesis_protocol/updates/",
)

_DIFF_PATH = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


@dataclass
class PatchVerification:
    """The verdict, plus the evidence that produced it."""

    accepted: bool
    patch_sha: str
    changed_paths: list[str] = field(default_factory=list)
    path_violations: list[str] = field(default_factory=list)
    secret_findings: list[str] = field(default_factory=list)
    tests_run: bool = False
    tests_passed: bool = False
    verifier_passed: bool | None = None
    verifier_score: float | None = None
    reasons: list[str] = field(default_factory=list)
    landed_sha: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "patch_sha": self.patch_sha,
            "changed_paths": list(self.changed_paths),
            "path_violations": list(self.path_violations),
            "secret_findings": list(self.secret_findings),
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "verifier_passed": self.verifier_passed,
            "verifier_score": self.verifier_score,
            "reasons": list(self.reasons),
            "landed_sha": self.landed_sha,
        }

    def evidence_block(self) -> str:
        """Markdown evidence record for the pull request body."""
        def mark(ok: bool) -> str:
            return "pass" if ok else "FAIL"

        if not self.tests_run:
            tests = "not run"
        else:
            tests = "passed" if self.tests_passed else "failed"
        verifier = (
            "not run"
            if self.verifier_passed is None
            else f"{mark(self.verifier_passed)} (score {self.verifier_score})"
        )
        return (
            "### Independent verification (Genesis gate)\n\n"
            f"- patch sha256: `{self.patch_sha}`\n"
            f"- changed files: {len(self.changed_paths)}\n"
            f"- path policy: {mark(not self.path_violations)}\n"
            f"- secret scan: {mark(not self.secret_findings)}\n"
            f"- tests re-run: {tests}\n"
            f"- independent verifier: {verifier}\n"
            f"- landed commit: `{self.landed_sha or 'pending'}`\n"
        )


def load_kernel_verification():
    """Load the V5 verifier + acceptance gate from their own package root.

    The package root inside ``genesis_v5`` is named ``genesis`` and is not
    importable from the repository root, so that directory is added to
    ``sys.path``. The two modules are pure-stdlib and the name does not collide
    with anything the product imports.
    """
    if _KERNEL_DIR not in sys.path:
        sys.path.insert(0, _KERNEL_DIR)
    from genesis.autonomy.acceptance import AcceptanceGate
    from genesis.qa.verifier import IndependentVerifier

    return AcceptanceGate, IndependentVerifier


def check_path_policy(changed_paths: list[str]) -> list[str]:
    """Return the changed paths that violate the protected-path policy."""
    violations: list[str] = []
    for path in changed_paths:
        clean = path.strip().lstrip("/")
        if not clean:
            continue
        if any(
            clean == prefix or clean.startswith(prefix)
            for prefix in PROTECTED_PREFIXES
        ):
            violations.append(clean)
    return violations


def parse_patch_paths(patch: str) -> list[str]:
    """Changed paths named by a unified diff, without applying it."""
    paths = [m.strip() for m in _DIFF_PATH.findall(patch) if m.strip() != "/dev/null"]
    seen: dict[str, None] = {}
    for p in paths:
        seen.setdefault(p, None)
    return list(seen)


def _git(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=cwd
    )


def create_scratch_worktree(base_ref: str, repo_root: str) -> str:
    """A detached worktree of ``base_ref`` in a throwaway temp directory.

    The caller is responsible for removing it (``remove_scratch_worktree``).
    """
    tmp = tempfile.mkdtemp(prefix="genesis-verify-")
    worktree = os.path.join(tmp, "wt")
    result = _git(
        "worktree", "add", "--detach", "--force", worktree, base_ref, cwd=repo_root
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"could not create a scratch worktree of {base_ref}: "
            f"{result.stderr.strip()[:200]}"
        )
    return worktree


def remove_scratch_worktree(worktree: str, repo_root: str) -> None:
    _git("worktree", "remove", "--force", worktree, cwd=repo_root)
    parent = os.path.dirname(worktree)
    try:
        os.rmdir(parent)
    except OSError:
        pass


def _apply_patch(worktree: str, patch: str) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "apply", "--index", "-"],
        input=patch,
        capture_output=True,
        text=True,
        cwd=worktree,
    )
    return proc.returncode == 0, (proc.stderr or "").strip()


def _changed_contents(worktree: str, changed_paths: list[str]) -> dict[str, str]:
    """Read the post-patch content of each changed path (missing -> "")."""
    contents: dict[str, str] = {}
    for path in changed_paths:
        full = os.path.join(worktree, path)
        try:
            with open(full, encoding="utf-8", errors="replace") as fh:
                contents[path] = fh.read()
        except OSError:
            contents[path] = ""
    return contents


def _run_in(worktree: str, command: str) -> tuple[bool, str]:
    """Run a test command inside the scratch worktree, not the real checkout."""
    proc = subprocess.run(
        shlex.split(command),
        capture_output=True,
        text=True,
        cwd=worktree,
        timeout=1800,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _test_evidence(ok: bool, output: str) -> str:
    """A short, independently produced statement about the test run.

    The verifier is a text heuristic that treats the word "error" as a failure
    marker, so raw pytest output (whose warnings can contain it) is a poor
    input. The exit status plus the final summary line is evidence without that
    trap — and it is produced by the run, not by the agent.
    """
    lines = [ln.strip() for ln in output.strip().splitlines() if ln.strip()]
    summary = lines[-1] if lines else "no output"
    return f"test run exit={'ok' if ok else 'fail'}: {summary}"


def verify_patch(
    patch: str,
    *,
    repo_root: str = _ROOT,
    base_ref: str = "origin/main",
    test_command: str | None = None,
    require_tests: bool = True,
    worktree_factory=None,
    gate=None,
    verifier=None,
) -> PatchVerification:
    """Verify an agent patch independently. Never raises for a bad patch.

    ``worktree_factory(base_ref) -> str`` and the ``gate`` / ``verifier``
    objects are injectable so the whole flow is testable without git or the
    kernel package.
    """
    patch_sha = hashlib.sha256(patch.encode("utf-8", "replace")).hexdigest()
    result = PatchVerification(accepted=False, patch_sha=patch_sha)

    if not patch.strip():
        result.reasons.append("empty patch")
        return result

    # 1. Path policy, read from the diff itself, before anything is applied.
    result.changed_paths = parse_patch_paths(patch)
    result.path_violations = check_path_policy(result.changed_paths)
    if result.path_violations:
        result.reasons.append(
            "patch touches protected paths: " + ", ".join(result.path_violations)
        )
        return result

    # 2. Apply the patch to a scratch worktree of the base branch.
    factory = worktree_factory or (lambda ref: create_scratch_worktree(ref, repo_root))
    worktree = None
    try:
        try:
            worktree = factory(base_ref)
        except Exception as exc:  # noqa: BLE001
            result.reasons.append(f"scratch worktree failed: {type(exc).__name__}")
            return result

        applied, apply_err = _apply_patch(worktree, patch)
        if not applied:
            result.reasons.append(f"patch did not apply: {apply_err[:200]}")
            return result

        # 3. Run the suite once against the patched tree; both the gate and the
        # verifier consume that single result.
        test_result: tuple[bool, str] | None = None
        if test_command:
            test_result = _run_in(worktree, test_command)

        if gate is None or verifier is None:
            try:
                AcceptanceGate, IndependentVerifier = load_kernel_verification()
            except Exception as exc:  # noqa: BLE001 - fail closed, never crash
                result.reasons.append(
                    f"verification modules unavailable: {type(exc).__name__}"
                )
                return result
            if gate is None:
                runner = (lambda: test_result) if test_result is not None else None
                gate = AcceptanceGate(
                    test_runner=runner, require_tests=require_tests
                )
            if verifier is None:
                verifier = IndependentVerifier()

        # 4. Acceptance gate: secret scan + tests on the actual diff.
        changes = _changed_contents(worktree, result.changed_paths)
        report = gate.evaluate(changes)
        result.secret_findings = list(report.secret_findings)
        result.tests_run = report.tests_run
        result.tests_passed = report.tests_passed
        if not report.accepted:
            result.reasons.extend(report.reasons or ["acceptance gate rejected"])
            return result

        # 5. Independent verifier scores the run's own evidence, never the
        # agent's prose.
        if test_result is not None:
            evidence = _test_evidence(*test_result)
        else:
            evidence = "no tests were run"
        outcome = verifier.verify(
            task="agent patch verification",
            result=evidence,
            producer_claim=None,
        )
        result.verifier_passed = outcome.passed
        result.verifier_score = outcome.score
        if not outcome.passed:
            result.reasons.append(
                "independent verifier rejected: " + "; ".join(outcome.issues)
            )
            return result

        result.accepted = True
        return result
    finally:
        if worktree:
            try:
                remove_scratch_worktree(worktree, repo_root)
            except Exception:  # noqa: BLE001 - cleanup must not mask the verdict
                pass


def main(argv: list[str] | None = None) -> int:
    """Verify a patch file and print the verdict. Used for manual checks."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: patch_verification.py <patch-file> [test-command]")
        return 2
    with open(args[0], encoding="utf-8", errors="replace") as fh:
        patch = fh.read()
    command = args[1] if len(args) > 1 else None
    result = verify_patch(
        patch, test_command=command, require_tests=bool(command)
    )
    import json

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
