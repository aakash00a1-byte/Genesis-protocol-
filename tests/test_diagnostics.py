"""Contract tests for cross-phase self-diagnostics (V7).

The diagnostics capability must observe without acting, degrade gracefully when
a phase is absent, and fail closed (report ``error``) when a check breaks.
"""
from __future__ import annotations


from genesis_protocol.diagnostics import (
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_MISSING,
    STATUS_OK,
    DiagnosticCheck,
    DiagnosticReport,
    Diagnostics,
    default_checks,
)


def _check(name, phase, outcome):
    return DiagnosticCheck(name, phase, lambda: outcome)


class TestCheckClassification:
    def test_ok(self):
        result = _check("c", "P1", (True, "fine")).run()
        assert result.status == STATUS_OK and result.severity == "info"

    def test_degraded_when_probe_reports_false(self):
        result = _check("c", "P1", (False, "not great")).run()
        assert result.status == STATUS_DEGRADED and result.severity == "medium"

    def test_missing_when_probe_reports_none(self):
        result = _check("c", "P9", (None, "absent")).run()
        assert result.status == STATUS_MISSING

    def test_error_when_probe_raises(self):
        def boom():
            raise RuntimeError("kaboom")

        result = DiagnosticCheck("c", "P1", boom).run()
        assert result.status == STATUS_ERROR and "kaboom" in result.detail
        assert result.severity == "high"


class TestReport:
    def test_healthy_when_ok_or_missing(self):
        report = DiagnosticReport()
        report.results = [_check("a", "P1", (True, "")).run(),
                          _check("b", "P9", (None, "")).run()]
        assert report.healthy is True

    def test_unhealthy_on_degraded(self):
        report = DiagnosticReport()
        report.results = [_check("a", "P1", (False, "x")).run()]
        assert report.healthy is False

    def test_to_dict_counts(self):
        report = DiagnosticReport()
        report.results = [_check("a", "P1", (True, "")).run(),
                          _check("b", "P1", (False, "")).run(),
                          _check("c", "P9", (None, "")).run()]
        data = report.to_dict()
        assert data["counts"] == {STATUS_OK: 1, STATUS_DEGRADED: 1, STATUS_MISSING: 1}


class TestDefaultBattery:
    def test_default_battery_runs_clean(self):
        report = Diagnostics(observability=None, audit=None).run()
        # No check should ever be an error on a healthy tree.
        assert all(r.status != STATUS_ERROR for r in report.results)

    def test_covers_the_key_phases(self):
        phases = {c.phase for c in default_checks()}
        assert {"P1/P2", "P2", "P3", "P8B", "P9", "P10"}.issubset(phases)

    def test_self_improve_gate_check_is_present_and_passes(self):
        """The battery must prove the autonomous gate still protects itself.

        Regression for the silent self-improvement outage: the battery verified
        other controls but never checked that the gate refuses an agent patch to
        its own harness. This check must exist and report ok on a healthy tree.
        """
        names = {c.name for c in default_checks()}
        assert "self_improve_gate_protected" in names
        result = next(
            r for r in Diagnostics(observability=None, audit=None).run().results
            if r.name == "self_improve_gate_protected"
        )
        assert result.status == STATUS_OK

    def test_self_improve_gate_check_degrades_when_refusal_is_gone(self, monkeypatch):
        """If the gate stops refusing harness self-modification, report degraded."""
        import sys
        import types

        fake = types.ModuleType("patch_verification")
        fake.check_path_policy = lambda paths: []  # refusal gone
        monkeypatch.setitem(sys.modules, "patch_verification", fake)

        probe = next(
            c for c in default_checks() if c.name == "self_improve_gate_protected"
        )
        result = probe.run()
        assert result.status == STATUS_DEGRADED
        assert "self_improve" in result.detail

    def test_absent_phase_is_missing_not_error(self):
        # With P9/P10 unmerged this must be 'missing', never 'error'.
        report = Diagnostics(observability=None, audit=None).run()
        evolution = next(r for r in report.results if r.name == "evolution_propose_only")
        assert evolution.status in (STATUS_MISSING, STATUS_OK)

    def test_phase_filter(self):
        report = Diagnostics(observability=None, audit=None).run(phases=["P3"])
        assert {r.phase for r in report.results} == {"P3"}


class TestNoSideEffects:
    def test_diagnostics_has_no_action_surface(self):
        diag = Diagnostics(observability=None, audit=None)
        exposed = {n for n in dir(diag) if not n.startswith("_")}
        forbidden = {"merge", "deploy", "push", "publish", "apply", "fix",
                     "restart", "kill", "set_secret", "respond"}
        assert forbidden.isdisjoint(exposed)

    def test_probes_are_read_only(self):
        # Running the battery twice yields the same verdicts (no state drift).
        first = Diagnostics(observability=None, audit=None).run().to_dict()
        second = Diagnostics(observability=None, audit=None).run().to_dict()
        assert first["counts"] == second["counts"]
