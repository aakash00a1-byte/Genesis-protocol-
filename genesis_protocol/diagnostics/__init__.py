"""Diagnostic runner (V7 cross-phase).

Runs the check battery, records a summary in the canonical observability manager
and - when a check is ``degraded`` or ``error`` - in the canonical
``SecurityEventLog`` (source ``diagnostics``). It takes no corrective action:
diagnosis and response are deliberately separate.
"""
from __future__ import annotations

from typing import Any, List, Optional

from genesis_protocol.diagnostics.checks import (
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_MISSING,
    STATUS_OK,
    DiagnosticCheck,
    DiagnosticReport,
    default_checks,
)


class Diagnostics:
    """Runs the cross-phase check battery and reports the result."""

    def __init__(
        self,
        checks: Optional[List[DiagnosticCheck]] = None,
        observability: Optional[Any] = None,
        audit: Optional[Any] = None,
    ):
        self.checks = checks if checks is not None else default_checks()
        self._obs = observability
        self._audit = audit

    @property
    def observability(self) -> Any:
        if self._obs is None:
            try:
                from genesis_protocol.observability import get_observability

                self._obs = get_observability("genesis-diagnostics")
            except Exception:
                self._obs = None
        return self._obs

    @property
    def audit(self) -> Any:
        if self._audit is None:
            try:
                from genesis_protocol.guardian.events import get_security_log

                self._audit = get_security_log()
            except Exception:
                self._audit = None
        return self._audit

    def run(self, phases: Optional[List[str]] = None) -> DiagnosticReport:
        report = DiagnosticReport()
        for check in self.checks:
            if phases and check.phase not in phases:
                continue
            report.results.append(check.run())
        self._emit(report)
        return report

    def _emit(self, report: DiagnosticReport) -> None:
        obs = self.observability
        if obs is not None:
            try:
                for result in report.results:
                    obs.record_metric(f"diagnostic.{result.name}",
                                      1.0 if result.status == STATUS_OK else 0.0)
            except Exception:
                pass
        audit = self.audit
        if audit is None:
            return
        for result in report.results:
            if result.status in (STATUS_ERROR, STATUS_DEGRADED):
                try:
                    audit.record(
                        "integrity", f"diagnostic_{result.status}",
                        severity="high" if result.status == STATUS_ERROR else "medium",
                        subject=result.name, source="diagnostics",
                        evidence={"phase": result.phase, "detail": result.detail},
                    )
                except Exception:
                    pass

    def status(self) -> dict:
        report = self.run()
        return report.to_dict()


__all__ = [
    "Diagnostics",
    "DiagnosticCheck",
    "DiagnosticReport",
    "default_checks",
    "STATUS_OK",
    "STATUS_DEGRADED",
    "STATUS_MISSING",
    "STATUS_ERROR",
]
