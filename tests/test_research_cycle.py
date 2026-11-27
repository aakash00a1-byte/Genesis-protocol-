"""The research cycle refuses to advance without evidence, and never deletes a failure."""

import json

import pytest

from genesis_protocol.research import (
    MissingEvidenceError,
    ResearchCycle,
    ResearchLedger,
    StageOrderError,
    VerificationRequiredError,
)
from genesis_protocol.research.hypothesis import HypothesisBook, HypothesisError

STAGE_EVIDENCE = {
    "question": {"question": "Is a|!a a tautology?", "why_it_matters": "core of classical logic"},
    "literature": {"sources": ["Law of excluded middle"], "summary": "standard result"},
    "hypothesis": {"statement": "a|!a is a tautology", "falsifiable_test": "exhaustive truth table"},
    "model": {"formalism": "propositional logic", "prediction": "true for all assignments"},
    "experiment": {"design": "exhaustive enumeration", "procedure": "evaluate both values of a"},
    "measurement": {"observations": ["a=false -> true", "a=true -> true"], "units": "assignments"},
    "verification": {"checker": "truth_table", "passed": True, "independent": True,
                     "produced_by": "human"},
    "report": {"path": "reports/excluded-middle.md", "summary": "a|!a holds for both values"},
}


@pytest.fixture
def ledger(tmp_path):
    return ResearchLedger(str(tmp_path / "ledger.jsonl"))


def _advance_through(cycle, upto):
    for stage in ["question", "literature", "hypothesis", "model",
                  "experiment", "measurement", "verification", "report"]:
        if stage == upto:
            return
        cycle.advance(stage, **STAGE_EVIDENCE[stage])


def test_stages_run_in_order(ledger):
    cycle = ResearchCycle("c1", ledger)
    assert cycle.stage == "question"
    cycle.advance("question", **STAGE_EVIDENCE["question"])
    assert cycle.stage == "literature"


def test_skipping_a_stage_is_refused(ledger):
    cycle = ResearchCycle("c1", ledger)
    with pytest.raises(StageOrderError):
        cycle.advance("hypothesis", **STAGE_EVIDENCE["hypothesis"])


def test_missing_evidence_is_refused(ledger):
    cycle = ResearchCycle("c1", ledger)
    with pytest.raises(MissingEvidenceError):
        cycle.advance("question", question="something", why_it_matters="")


def test_verification_must_pass_and_be_independent(ledger):
    cycle = ResearchCycle("c1", ledger)
    _advance_through(cycle, "verification")
    with pytest.raises(VerificationRequiredError):
        cycle.advance("verification", checker="truth_table", passed=False, independent=True)
    with pytest.raises(VerificationRequiredError):
        cycle.advance("verification", checker="truth_table", passed=True, independent=False)


def test_a_producer_cannot_verify_itself(ledger):
    cycle = ResearchCycle("c1", ledger)
    _advance_through(cycle, "verification")
    with pytest.raises(VerificationRequiredError):
        cycle.advance("verification", checker="truth_table", passed=True,
                      independent=True, produced_by="truth_table")


def test_report_requires_a_verified_result(ledger):
    cycle = ResearchCycle("c1", ledger)
    _advance_through(cycle, "verification")
    assert cycle.can_claim_discovery()["verified"] is False
    assert cycle.can_claim_discovery()["claim_allowed"] is False

    cycle.advance("verification", **STAGE_EVIDENCE["verification"])
    # verified, but nothing is written down yet - still not a claim
    assert cycle.can_claim_discovery()["report_written"] is False
    assert cycle.can_claim_discovery()["claim_allowed"] is False

    cycle.advance("report", **STAGE_EVIDENCE["report"])
    claim = cycle.can_claim_discovery()
    assert claim["claim_allowed"] is True
    assert claim["verified"] is True


def test_a_failing_check_is_not_accepted_as_verification(ledger):
    cycle = ResearchCycle("c1", ledger)
    _advance_through(cycle, "verification")
    with pytest.raises(VerificationRequiredError):
        cycle.advance("verification", checker="truth_table", passed=False, independent=True)
    assert cycle.stage == "verification"      # it did not move on


def test_the_full_cycle_records_every_stage_in_the_ledger(ledger):
    cycle = ResearchCycle("c1", ledger)
    for stage, evidence in STAGE_EVIDENCE.items():
        cycle.advance(stage, **evidence)
    kinds = [e["kind"] for e in ledger.entries(cycle_id="c1")]
    assert kinds[0] == "cycle_opened"
    assert kinds[-1] == "stage:report"
    assert ledger.verify()["ok"] is True


def test_the_ledger_detects_tampering(ledger, tmp_path):
    cycle = ResearchCycle("c1", ledger)
    cycle.advance("question", **STAGE_EVIDENCE["question"])
    assert ledger.verify()["ok"] is True

    path = tmp_path / "ledger.jsonl"
    lines = path.read_text().splitlines()
    tampered = json.loads(lines[-1])
    tampered["payload"]["question"] = "a different question"
    lines[-1] = json.dumps(tampered, sort_keys=True)
    path.write_text("\n".join(lines) + "\n")

    verdict = ledger.verify()
    assert verdict["ok"] is False
    assert verdict["broken_at"] == 1


def test_the_ledger_cannot_delete(ledger):
    with pytest.raises(PermissionError):
        ledger.remove(0)


def test_a_hypothesis_needs_a_falsifiable_test():
    book = HypothesisBook()
    with pytest.raises(HypothesisError):
        book.add("h1", "something vague", falsifiable_test="")


def test_support_requires_an_independent_passing_check():
    book = HypothesisBook()
    book.add("h1", "a|!a is a tautology", "truth table")
    with pytest.raises(HypothesisError):
        book.support("h1", {"passed": True, "independent": False})
    with pytest.raises(HypothesisError):
        book.support("h1", {"passed": False, "independent": True})
    book.support("h1", {"passed": True, "independent": True, "checker": "truth_table"})
    assert book.get("h1").status == "supported"


def test_a_refuted_hypothesis_is_permanent():
    book = HypothesisBook()
    book.add("h1", "a -> b is a tautology", "truth table")
    book.refute("h1", "counterexample a=true,b=false")
    assert book.get("h1").status == "refuted"
    assert len(book.refuted()) == 1
    with pytest.raises(HypothesisError):
        book.support("h1", {"passed": True, "independent": True})
    with pytest.raises(PermissionError):
        book.remove("h1")
    assert book.get("h1").evidence[0]["reason"].startswith("counterexample")


def test_a_new_hypothesis_can_supersede_a_refuted_one_without_hiding_it():
    book = HypothesisBook()
    book.add("h1", "a -> b is a tautology", "truth table")
    book.add("h2", "(a -> b) | (b -> a) is a tautology", "truth table")
    book.refute("h1", "counterexample")
    book.supersede("h1", "h2")
    assert book.get("h1").superseded_by == "h2"
    assert book.get("h1").status == "refuted"
    assert len(book.refuted()) == 1
