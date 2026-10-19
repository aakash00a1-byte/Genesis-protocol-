"""Acceptance gate: a code change is not accepted until checks pass.

A change (a mapping of ``path -> new content``) is evaluated before the loop
will call a run successful:

  1. **Secret scan** — every changed file's content is scanned with the same
     ``Redactor`` used by audit and memory. A change that would introduce a
     secret is rejected.
  2. **Tests** — a test runner is invoked. Offline by default the runner is
     ``None`` and the gate reports ``tests_run=False``; a real caller injects
     ``python -m pytest`` (or any command). This keeps the gate usable offline
     while making the requirement explicit.

The gate never writes files and never runs a shell itself unless a runner is
injected — it only decides. That keeps it safe to call from an autonomous loop.
"""
from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from genesis.security.redaction import Redactor


@dataclass
class AcceptanceReport:
    accepted: bool
    tests_run: bool = False
    tests_passed: bool = False
    secret_findings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "secret_findings": list(self.secret_findings),
            "reasons": list(self.reasons),
        }


# A runner takes no arguments and returns (passed, output).
TestRunner = Callable[[], "tuple[bool, str]"]


class AcceptanceGate:
    def __init__(
        self,
        *,
        test_runner: TestRunner | None = None,
        redactor: Redactor | None = None,
        require_tests: bool = False,
    ) -> None:
        self._runner = test_runner
        self._redactor = redactor or Redactor()
        self.require_tests = require_tests

    @staticmethod
    def command_runner(command: str) -> TestRunner:
        """Build a runner from a command string (no shell, argv only)."""

        def run() -> tuple[bool, str]:
            proc = subprocess.run(  # noqa: S603 - argv, no shell, caller-provided
                shlex.split(command),
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode == 0, output

        return run

    # ------------------------------------------------------------------
    def evaluate(self, changes: dict[str, str]) -> AcceptanceReport:
        report = AcceptanceReport(accepted=False)

        # 1. Secret scan.
        for path, content in changes.items():
            redacted = self._redactor.redact(content)
            if redacted != content:
                report.secret_findings.append(path)
        if report.secret_findings:
            report.reasons.append(
                "secret detected in: " + ", ".join(sorted(report.secret_findings))
            )
            return report

        # 2. Tests.
        if self._runner is not None:
            report.tests_run = True
            passed, output = self._runner()
            report.tests_passed = bool(passed)
            if not passed:
                report.reasons.append("tests failed: " + output.strip()[-500:])
                return report
        elif self.require_tests:
            report.reasons.append("tests were required but no runner is configured")
            return report

        report.accepted = True
        return report
