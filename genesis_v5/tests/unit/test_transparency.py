"""Tests for the transparency layer: no hidden failures, visible benefits."""
from __future__ import annotations

import pytest

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.kernel.kernel import KernelRequest
from genesis.transparency.ledger import (
    DecisionLedger,
    FailureLedger,
    TransparencyReport,
)


def test_decision_records_rationale_and_expected_benefit() -> None:
    ledger = DecisionLedger()
    decision = ledger.record(
        actor="tester",
        question="Which path?",
        chosen="coordinator",
        rationale="coordinator available",
        expected_benefit="verified multi-agent result",
        options=["coordinator", "direct"],
    )
    assert decision.rationale == "coordinator available"
    assert decision.expected_benefit == "verified multi-agent result"
    assert decision.outcome == "pending"


def test_resolve_closes_the_benefit_loop() -> None:
    ledger = DecisionLedger()
    decision = ledger.record(
        actor="tester",
        question="Which path?",
        chosen="direct",
        rationale="no coordinator",
        expected_benefit="a result",
    )
    ledger.resolve(
        decision.decision_id, outcome="success", actual_benefit="result produced"
    )
    report = ledger.benefit_report()
    assert report[0]["outcome"] == "success"
    assert report[0]["benefit_delivered"] is True
    assert ledger.unresolved() == []


def test_failure_guard_records_and_reraises() -> None:
    ledger = FailureLedger()
    with pytest.raises(ValueError):
        with ledger.guard(component="x", what="boom", impact="none"):
            raise ValueError("boom")
    assert ledger.count() == 1
    assert ledger.failures()[0].surfaced is True
    assert "ValueError" in ledger.failures()[0].why


def test_failure_capture_records_and_continues() -> None:
    ledger = FailureLedger()
    with ledger.capture(component="x", what="degraded", impact="reduced context"):
        raise RuntimeError("soft failure")
    assert ledger.count() == 1
    assert ledger.failures()[0].impact == "reduced context"


def test_kernel_run_records_a_resolved_decision() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    response = kernel.run(KernelRequest(task="summarize the build status", actor="u"))
    assert response.ok

    decisions = kernel.transparency.decisions.decisions()
    assert len(decisions) == 1
    assert decisions[0].outcome == "success"
    assert decisions[0].expected_benefit
    assert decisions[0].actual_benefit
    assert kernel.transparency.decisions.unresolved() == []


def test_snapshot_reports_zero_hidden_failures() -> None:
    report = TransparencyReport()
    report.decisions.record(
        actor="u",
        question="q",
        chosen="c",
        rationale="r",
        expected_benefit="b",
    )
    snapshot = report.snapshot()
    assert snapshot["hidden_failures"] == 0
    assert len(snapshot["decisions"]) == 1
    assert snapshot["failure_count"] == 0
