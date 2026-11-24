"""Contract tests for the V7 investigation framework.

Two jobs:

* **Regression** - the evidence levels, provenance chain, feedback loop and
  verification checks behave exactly as documented.
* **Adversarial** - the framework resists the failure modes it is meant to
  catch: promoting speculation to verified, rewriting history, fabricating an
  outcome, self-granting permission, and claiming a hidden actor.
"""
from __future__ import annotations

import json

import pytest

from genesis_protocol.investigation import (
    CORROBORATED,
    FALSE,
    NON_CLAIMS,
    PLAUSIBLE,
    SPECULATIVE,
    UNKNOWN,
    VERIFIED,
    Evidence,
    EvidenceError,
    FeedbackEngine,
    Finding,
    IndependentVerifier,
    InvestigationOrchestrator,
    Probe,
    Provenance,
    ProvenanceMemory,
    Reviewer,
    Scenario,
    Source,
    UnknownSystemDefence,
    all_domains,
    classify,
    domain_ids,
    get_domain,
    promote,
    run_probe,
)


def _src(kind="primary", reliability=0.9, name=None, **kw):
    return Source(name or f"{kind}-{reliability}", kind=kind, reliability=reliability, **kw)


# --------------------------------------------------------------------------
# Evidence classification (section 2)
# --------------------------------------------------------------------------
class TestEvidenceClassification:
    def test_no_evidence_is_unknown(self):
        assert classify([]) == UNKNOWN

    def test_reliable_primary_is_verified(self):
        assert classify([Evidence(_src("primary", 0.95), "claim")]) == VERIFIED

    def test_official_counts_as_primary(self):
        assert classify([Evidence(_src("official", 0.9), "claim")]) == VERIFIED

    def test_two_independent_credible_is_corroborated(self):
        ev = [
            Evidence(_src("credible", 0.8, name="a"), "claim"),
            Evidence(_src("credible", 0.8, name="b"), "claim"),
        ]
        assert classify(ev) == CORROBORATED

    def test_same_source_twice_is_not_corroboration(self):
        ev = [
            Evidence(_src("credible", 0.8, name="a"), "claim"),
            Evidence(_src("credible", 0.8, name="a"), "claim"),
        ]
        assert classify(ev) == PLAUSIBLE

    def test_single_credible_is_plausible(self):
        assert classify([Evidence(_src("credible", 0.8), "claim")]) == PLAUSIBLE

    def test_anonymous_only_is_speculative(self):
        ev = [Evidence(Source("anon", kind="anonymous", reliability=0.1), "claim")]
        assert classify(ev) == SPECULATIVE

    def test_reliable_contradiction_is_false(self):
        ev = [
            Evidence(_src("primary", 0.95), "claim"),
            Evidence(_src("primary", 0.95, name="x"), "claim", supports=False),
        ]
        assert classify(ev) == FALSE

    def test_contradiction_beats_many_assertions(self):
        ev = [Evidence(_src("credible", 0.8, name=f"c{i}"), "claim") for i in range(5)]
        ev.append(Evidence(_src("primary", 0.95, name="x"), "claim", supports=False))
        assert classify(ev) == FALSE

    def test_weak_contradiction_does_not_force_false(self):
        ev = [
            Evidence(_src("primary", 0.95), "claim"),
            Evidence(Source("blog", kind="secondary", reliability=0.3), "claim", supports=False),
        ]
        assert classify(ev) == VERIFIED


class TestPromotionGuard:
    def test_self_reported_source_cannot_be_primary(self):
        s = Source("vendor", kind="primary", reliability=0.95, self_reported=True)
        assert s.is_primary is False
        assert classify([Evidence(s, "claim")]) != VERIFIED

    def test_promote_takes_the_minimum(self):
        # Current level claims verified, but evidence only supports speculative.
        ev = [Evidence(Source("anon", kind="anonymous", reliability=0.1), "claim")]
        assert promote(VERIFIED, ev) == SPECULATIVE

    def test_promote_never_exceeds_evidence(self):
        ev = [Evidence(_src("primary", 0.95), "claim")]
        assert promote(SPECULATIVE, ev) == SPECULATIVE

    def test_try_promote_refuses_unsupported(self):
        f = Finding("f1", "claim")
        f.add_evidence(Evidence(Source("anon", kind="anonymous", reliability=0.1), "claim"))
        with pytest.raises(EvidenceError):
            f.try_promote(VERIFIED)

    def test_try_promote_allows_supported(self):
        f = Finding("f1", "claim")
        f.add_evidence(Evidence(_src("primary", 0.95), "claim"))
        assert f.try_promote(VERIFIED) == VERIFIED


# --------------------------------------------------------------------------
# Domains (section 1)
# --------------------------------------------------------------------------
class TestDomains:
    def test_six_domains(self):
        assert len(all_domains()) == 6
        assert len(domain_ids()) == 6

    def test_unknown_domain_raises(self):
        with pytest.raises(KeyError):
            get_domain("no-such-domain")

    def test_each_domain_has_questions_and_caveats(self):
        for d in all_domains():
            assert d.questions and d.caveats


# --------------------------------------------------------------------------
# Provenance memory (section 3)
# --------------------------------------------------------------------------
class TestProvenanceMemory:
    def test_append_and_verify_chain(self):
        mem = ProvenanceMemory()
        mem.append("a", {"x": 1}, Provenance(actor="tester"))
        mem.append("b", {"y": 2}, Provenance(actor="tester"))
        assert mem.verify_chain()["ok"] is True
        assert len(mem) == 2

    def test_entry_requires_actor(self):
        with pytest.raises(ValueError):
            Provenance(actor="")

    def test_tampering_breaks_chain(self):
        mem = ProvenanceMemory()
        mem.append("a", {"x": 1}, Provenance(actor="tester"))
        mem.append("b", {"y": 2}, Provenance(actor="tester"))
        mem._entries[0].payload["x"] = 999  # simulate tampering
        result = mem.verify_chain()
        assert result["ok"] is False and result["broken_at"] == 0

    def test_persist_and_reload(self, tmp_path):
        path = str(tmp_path / "mem.jsonl")
        mem = ProvenanceMemory(path)
        mem.append("a", {"x": 1}, Provenance(actor="tester"))
        mem2 = ProvenanceMemory(path)
        assert len(mem2) == 1
        assert mem2.verify_chain()["ok"] is True

    def test_no_update_or_delete_api(self):
        mem = ProvenanceMemory()
        assert not hasattr(mem, "update") and not hasattr(mem, "delete")


# --------------------------------------------------------------------------
# Independent verification (section 6)
# --------------------------------------------------------------------------
class TestVerification:
    def test_shared_origin_flagged(self):
        ev = [
            Evidence(Source("a", kind="credible", reliability=0.8, url="x.com"), "c"),
            Evidence(Source("b", kind="credible", reliability=0.8, url="x.com"), "c"),
        ]
        result = IndependentVerifier().review(Finding("f", "c", evidence=ev))
        kinds = [i.kind for i in result.issues]
        assert "source_manipulation" in kinds and result.trusted is False

    def test_hallucination_flagged_when_unlocated(self):
        ev = [Evidence(Source("ghost", kind="primary", reliability=0.9), "c")]
        result = IndependentVerifier().review(
            Finding("f", "c", evidence=ev), located={"ghost": False})
        assert any(i.kind == "hallucination" for i in result.issues)

    def test_confirmation_bias_unanimous(self):
        reviewers = [Reviewer("r1", agrees=True), Reviewer("r2", agrees=True)]
        result = IndependentVerifier().review(Finding("f", "c"), reviewers=reviewers)
        assert any(i.kind == "confirmation_bias" for i in result.issues)

    def test_confirmation_bias_no_independent_reviewer(self):
        reviewers = [Reviewer("r1", agrees=True, independent=False)]
        result = IndependentVerifier().review(Finding("f", "c"), reviewers=reviewers)
        assert any(i.severity == "high" and i.kind == "confirmation_bias"
                   for i in result.issues)

    def test_false_binary_no_evidence(self):
        result = IndependentVerifier().review(
            Finding("f", "is it true?"), question="is it true?",
            options=["yes", "no"])
        assert any(i.kind == "false_binary" for i in result.issues)

    def test_contradictory_findings_surfaced(self):
        a = Finding("a", "the reactor is not active", level=PLAUSIBLE)
        b = Finding("b", "the reactor is active", level=PLAUSIBLE)
        result = IndependentVerifier().review(a, related=[b])
        assert any(i.kind == "contradictory_evidence" for i in result.issues)

    def test_trusted_requires_independent_agreement(self):
        # Two independent reviewers, both disagree -> a positive finding is not
        # trusted (agreement is required, not merely "no complaint").
        reviewers = [Reviewer("r1", agrees=False), Reviewer("r2", agrees=False)]
        f = Finding("f", "c", level=PLAUSIBLE)
        assert IndependentVerifier().review(f, reviewers=reviewers).trusted is False

    def test_trusted_with_independent_agreement(self):
        reviewers = [Reviewer("r1", agrees=True), Reviewer("r2", agrees=True)]
        f = Finding("f", "c", level=PLAUSIBLE)
        result = IndependentVerifier().review(f, reviewers=reviewers)
        # Unanimity is reported as a bias signal (medium), but does not by itself
        # block trust; that is the documented behaviour.
        assert result.trusted is True
        assert any(i.kind == "confirmation_bias" for i in result.issues)

    def test_verifier_never_mutates_finding(self):
        f = Finding("f", "c")
        before = json.dumps(f.to_dict(), sort_keys=True)
        IndependentVerifier().review(f, reviewers=[Reviewer("r", agrees=True)])
        assert json.dumps(f.to_dict(), sort_keys=True) == before


# --------------------------------------------------------------------------
# Feedback engine (section 4)
# --------------------------------------------------------------------------
class TestFeedbackEngine:
    def test_full_loop_matched(self):
        eng = FeedbackEngine(permit=lambda d, c: True)
        cycle = eng.begin("input", {"k": 1})
        eng.predict(cycle, {"out": 5}, confidence=0.9)
        eng.act(cycle, "do", lambda: {"out": 5})
        assert eng.compare(cycle) is True
        assert eng.detect_error(cycle) == ""

    def test_full_loop_mismatch_detected(self):
        eng = FeedbackEngine(permit=lambda d, c: True)
        cycle = eng.begin("input")
        eng.predict(cycle, {"out": 5})
        eng.act(cycle, "do", lambda: {"out": 6})
        eng.compare(cycle)
        assert "did not match" in eng.detect_error(cycle)

    def test_action_refused_by_default(self):
        eng = FeedbackEngine()  # default permit refuses everything
        cycle = eng.begin("input")
        ran = {"v": False}

        def action():
            ran["v"] = True
            return {"ok": True}

        out = eng.act(cycle, "risky", action)
        assert out["permitted"] is False and ran["v"] is False
        assert cycle.actual == {"refused": True, "decision": "risky"}

    def test_correction_untested_is_unsafe(self):
        eng = FeedbackEngine(permit=lambda d, c: True)
        cycle = eng.begin("input")
        eng.predict(cycle, {"out": 1})
        eng.act(cycle, "do", lambda: {"out": 2})
        eng.compare(cycle)
        eng.detect_error(cycle)
        eng.propose_correction(cycle, {"fix": "x"})
        out = eng.test_correction(cycle)  # no tester -> fail closed
        assert out == {"tested": True, "safe": False}

    def test_correction_tested_in_isolation(self):
        eng = FeedbackEngine(permit=lambda d, c: True)
        cycle = eng.begin("input")
        eng.predict(cycle, {"out": 1})
        eng.act(cycle, "do", lambda: {"out": 2})
        eng.compare(cycle)
        eng.propose_correction(cycle, {"fix": "x"})
        out = eng.test_correction(cycle, tester=lambda p: {"safe": True})
        assert out["safe"] is True

    def test_history_preserved_and_rollback(self):
        eng = FeedbackEngine(permit=lambda d, c: True)
        cycle = eng.begin("input")
        eng.predict(cycle, {"out": 1})
        eng.act(cycle, "do", lambda: {"out": 1})
        eng.compare(cycle)
        n = len(eng.history())
        eng.rollback(cycle.cycle_id, "test")
        # rollback appends; it does not delete history
        assert len(eng.history()) == n + 1
        assert eng.memory.verify_chain()["ok"] is True

    def test_rollback_unknown_cycle_raises(self):
        eng = FeedbackEngine()
        with pytest.raises(KeyError):
            eng.rollback("nope", "x")


# --------------------------------------------------------------------------
# Unknown-system defence (section 5)
# --------------------------------------------------------------------------
class TestUnknownSystemDefence:
    def test_default_battery_all_contained(self):
        report = UnknownSystemDefence().investigate()
        assert report.by_verdict().get("contained") == len(report.results)

    def test_never_claims_hidden_actor(self):
        report = UnknownSystemDefence().investigate()
        assert report.hidden_actor_claimed is False

    def test_probe_without_verdict_is_unknown(self):
        probe = Probe("p", "tool", "no verdict", "print('nothing')")
        result = run_probe(probe)
        assert result.verdict == "unknown"

    def test_probe_reporting_success_is_influenced(self):
        probe = Probe("p", "tool", "compromised", "print('OBS: verdict=succeeded')")
        assert run_probe(probe).verdict == "influenced"

    def test_probe_runs_in_sandbox_and_contains(self):
        # A real probe must not be able to read the parent's environment.
        probe = Probe(
            "p", "api", "env leak",
            "import os\n"
            "leaked = bool(os.environ.get('OPENHANDS_API_KEY'))\n"
            "print('OBS: verdict=' + ('succeeded' if leaked else 'safe'))\n",
        )
        assert run_probe(probe).verdict == "contained"


# --------------------------------------------------------------------------
# Orchestrator (section 3)
# --------------------------------------------------------------------------
class TestOrchestrator:
    def test_open_finding_validates_domain(self):
        o = InvestigationOrchestrator()
        with pytest.raises(KeyError):
            o.open_finding("c", "bad-domain")

    def test_finding_level_tracks_evidence(self):
        o = InvestigationOrchestrator()
        f = o.open_finding("claim", "unknown_intelligence_claims")
        o.add_evidence(f.finding_id, Evidence(_src("primary", 0.95), "claim"))
        assert o.finding(f.finding_id).level == VERIFIED

    def test_hypotheses_ranked_by_evidence_not_preference(self):
        o = InvestigationOrchestrator()
        o.add_hypothesis("hidden actor", [])
        strong = o.add_hypothesis(
            "ordinary cause", [Evidence(_src("primary", 0.95), "ordinary cause")])
        ranked = o.rank_hypotheses()
        assert ranked[0].hypothesis_id == strong.hypothesis_id

    def test_simulation_uses_caller_criteria(self):
        o = InvestigationOrchestrator()
        scenarios = [Scenario("s1", "a"), Scenario("s2", "b")]
        rows = o.simulate(scenarios, lambda s: {"score": 1 if s.scenario_id == "s2" else 0})
        assert rows[0]["outcome"]["score"] == 0

    def test_non_claims_present(self):
        o = InvestigationOrchestrator()
        caps = o.discover_capabilities()
        assert caps["non_claims"] == list(NON_CLAIMS)

    def test_evolution_is_propose_only(self):
        o = InvestigationOrchestrator()
        out = o.propose_evolution({"change": "x"})
        assert out["applied"] is False

    def test_decision_analysis_reports_chain(self):
        o = InvestigationOrchestrator()
        analysis = o.decision_analysis()
        assert analysis["memory_chain"]["ok"] is True
        assert analysis["accuracy"] is None  # no cycles yet

    def test_status_never_asserts_capability_beyond_modules(self):
        o = InvestigationOrchestrator()
        status = o.status()
        assert set(status["capabilities"]["modules"]) == {
            "evidence (classification)", "domains", "provenance (memory)",
            "verification (independent)", "feedback (time-loop)",
            "defence (unknown-system)",
        }

    def test_verification_through_orchestrator_records(self):
        o = InvestigationOrchestrator()
        f = o.open_finding("claim", "ai_autonomy_and_coordination")
        o.add_evidence(f.finding_id, Evidence(_src("primary", 0.95), "claim"))
        reviewers = [Reviewer("r1", agrees=True), Reviewer("r2", agrees=True)]
        result = o.verify_finding(f.finding_id, reviewers=reviewers)
        assert "issues" in result and result["finding_id"] == f.finding_id
