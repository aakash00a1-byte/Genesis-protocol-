"""Investigation orchestrator (V7 investigation).

A modular intelligence orchestrator for evidence-driven investigation. It is
deliberately *not* claimed to be conscious, unlimited or unrestricted: it is a
bookkeeping-and-reasoning harness over the other modules, and every capability
it exposes can only *record*, *classify*, *compare* or *refuse*. It never
performs an action on the real system.

Capabilities, each delegated to a module:

* **Persistent, provenance-aware memory** -> ``provenance.ProvenanceMemory``.
* **Historical decision analysis** -> ``history`` / ``decision_analysis`` over
  recorded cycles and findings.
* **Multi-hypothesis reasoning** -> ``hypotheses`` ranks competing explanations
  by the strength of the evidence that supports each, never by preference.
* **Scenario simulation and outcome comparison** -> ``simulate`` compares
  scenarios by explicit, caller-supplied criteria (no hidden scoring).
* **Independent specialist agents** -> ``specialists`` are named reviewers; the
  orchestrator can attach them to a verification but cannot fabricate their
  agreement.
* **Continuous feedback and error correction** -> ``FeedbackEngine``.
* **Capability discovery and controlled evolution** -> ``discover_capabilities``
  reports what is present; ``propose_evolution`` only ever *proposes* (it does
  not apply), reusing the P9 propose-only discipline.

The orchestrator records everything to memory with provenance and never rewrites
history.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from genesis_protocol.investigation.domains import all_domains, domain_ids, get_domain
from genesis_protocol.investigation.evidence import (
    LEVEL_ORDER,
    Evidence,
    Finding,
    classify,
)
from genesis_protocol.investigation.feedback import FeedbackEngine
from genesis_protocol.investigation.provenance import Provenance, ProvenanceMemory
from genesis_protocol.investigation.verification import IndependentVerifier, Reviewer

# Explicit non-claims, surfaced in every status so a reader is never misled.
NON_CLAIMS = (
    "Not conscious.",
    "Not unlimited intelligence.",
    "Not unrestricted autonomy.",
)


@dataclass
class Hypothesis:
    """A competing explanation for the same question, with its evidence."""

    hypothesis_id: str
    statement: str
    evidence: List[Evidence] = field(default_factory=list)

    @property
    def level(self) -> str:
        return classify(self.evidence)

    @property
    def strength(self) -> int:
        return LEVEL_ORDER.index(self.level)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement,
            "level": self.level,
            "evidence_count": len(self.evidence),
        }


@dataclass
class Scenario:
    """A candidate course of action with its stated predicted outcome."""

    scenario_id: str
    description: str
    predicted: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"scenario_id": self.scenario_id, "description": self.description,
                "predicted": dict(self.predicted)}


class InvestigationOrchestrator:
    """Coordinates evidence, hypotheses, simulation, feedback and verification."""

    def __init__(
        self,
        memory: Optional[ProvenanceMemory] = None,
        verifier: Optional[IndependentVerifier] = None,
        feedback: Optional[FeedbackEngine] = None,
    ):
        self.memory = memory or ProvenanceMemory()
        self.verifier = verifier or IndependentVerifier()
        self.feedback = feedback or FeedbackEngine(memory=self.memory)
        self._findings: Dict[str, Finding] = {}
        self._hypotheses: Dict[str, Hypothesis] = {}
        self._specialists: Dict[str, Reviewer] = {}
        self._counter = 0

    # -- domains -------------------------------------------------------------
    def domains(self) -> List[Dict[str, Any]]:
        return [d.to_dict() for d in all_domains()]

    # -- findings ------------------------------------------------------------
    def open_finding(self, claim: str, domain: str) -> Finding:
        get_domain(domain)  # validate; unknown domain is an error
        self._counter += 1
        fid = f"finding-{self._counter:04d}"
        finding = Finding(finding_id=fid, claim=claim, domain=domain)
        self._findings[fid] = finding
        self.memory.append("finding.opened", {"finding_id": fid, "claim": claim,
                                              "domain": domain},
                           Provenance(actor="orchestrator", method="investigate"))
        return finding

    def add_evidence(self, finding_id: str, evidence: Evidence) -> str:
        finding = self._require(finding_id)
        level = finding.add_evidence(evidence)
        self.memory.append("finding.evidence",
                           {"finding_id": finding_id, "level": level,
                            "claim": evidence.claim, "supports": evidence.supports},
                           Provenance(actor="orchestrator", method="record"))
        return level

    def findings(self) -> List[Finding]:
        return list(self._findings.values())

    def finding(self, finding_id: str) -> Optional[Finding]:
        return self._findings.get(finding_id)

    def _require(self, finding_id: str) -> Finding:
        if finding_id not in self._findings:
            raise KeyError(f"unknown finding '{finding_id}'")
        return self._findings[finding_id]

    # -- multi-hypothesis reasoning -----------------------------------------
    def add_hypothesis(self, statement: str, evidence: Optional[List[Evidence]] = None) -> Hypothesis:
        hid = f"hyp-{len(self._hypotheses) + 1:04d}"
        hyp = Hypothesis(hypothesis_id=hid, statement=statement, evidence=list(evidence or []))
        self._hypotheses[hid] = hyp
        self.memory.append("hypothesis.added", {"hypothesis_id": hid, "statement": statement},
                           Provenance(actor="orchestrator", method="reason"))
        return hyp

    def rank_hypotheses(self) -> List[Hypothesis]:
        """Rank by evidence strength; ties broken by id (stable, no preference)."""
        return sorted(self._hypotheses.values(),
                      key=lambda h: (-h.strength, h.hypothesis_id))

    # -- scenario simulation -------------------------------------------------
    def simulate(self, scenarios: List[Scenario],
                 criteria: Callable[[Scenario], Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compare scenarios using caller-supplied criteria.

        The orchestrator does not invent a score. It records the criteria's
        output per scenario and leaves the ranking to the caller, so no hidden
        preference enters the decision.
        """
        rows = []
        for s in scenarios:
            rows.append({"scenario": s.to_dict(), "outcome": dict(criteria(s) or {})})
        self.memory.append("simulation.recorded", {"count": len(rows)},
                           Provenance(actor="orchestrator", method="simulate"))
        return rows

    # -- independent specialists --------------------------------------------
    def register_specialist(self, reviewer: Reviewer) -> None:
        self._specialists[reviewer.name] = reviewer
        self.memory.append("specialist.registered", {"name": reviewer.name},
                           Provenance(actor="orchestrator", method="register"))

    def specialists(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._specialists.values()]

    def verify_finding(self, finding_id: str, reviewers: Optional[List[Reviewer]] = None,
                       located: Optional[Dict[str, bool]] = None,
                       question: str = "", options: Optional[List[str]] = None) -> Dict[str, Any]:
        finding = self._require(finding_id)
        panel = list(reviewers) if reviewers is not None else list(self._specialists.values())
        result = self.verifier.review(finding, reviewers=panel, located=located,
                                      question=question, options=options,
                                      related=self.findings())
        self.memory.append("finding.verified",
                           {"finding_id": finding_id, "trusted": result.trusted,
                            "issues": [i.kind for i in result.issues]},
                           Provenance(actor="orchestrator", method="verify"))
        return result.to_dict()

    # -- historical decision analysis ---------------------------------------
    def decision_analysis(self) -> Dict[str, Any]:
        """Summarise recorded decisions and their prediction accuracy."""
        cycles = self.feedback.memory.entries("cycle.comparison")
        matched = sum(1 for c in cycles if c.payload.get("matched"))
        total = len(cycles)
        errors = [c.payload for c in self.feedback.memory.entries("cycle.error")]
        return {
            "cycles_compared": total,
            "cycles_matched": matched,
            "accuracy": (matched / total) if total else None,
            "errors": errors,
            "memory_chain": self.memory.verify_chain(),
        }

    # -- capability discovery ------------------------------------------------
    def discover_capabilities(self) -> Dict[str, Any]:
        """Report what the investigation layer actually has, not what it claims."""
        return {
            "domains": domain_ids(),
            "modules": [
                "evidence (classification)",
                "domains",
                "provenance (memory)",
                "verification (independent)",
                "feedback (time-loop)",
                "defence (unknown-system)",
            ],
            "findings": len(self._findings),
            "hypotheses": len(self._hypotheses),
            "specialists": len(self._specialists),
            "non_claims": list(NON_CLAIMS),
        }

    def propose_evolution(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        """Record an evolution *proposal* only. Never applies anything.

        This mirrors the P9 propose-only discipline: the proposal is recorded
        with provenance and returned marked ``applied: False``. Applying change
        is out of scope for this layer.
        """
        record = {"proposal": dict(proposal or {}), "applied": False}
        self.memory.append("evolution.proposed", record,
                           Provenance(actor="orchestrator", method="propose"))
        return record

    # -- status --------------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        return {
            "capabilities": self.discover_capabilities(),
            "findings": [f.to_dict() for f in self.findings()],
            "hypotheses": [h.to_dict() for h in self.rank_hypotheses()],
            "decision_analysis": self.decision_analysis(),
            "non_claims": list(NON_CLAIMS),
        }


def get_orchestrator(path: Optional[str] = None) -> InvestigationOrchestrator:
    """Process-wide orchestrator (memory file path from GLUTEN_INVESTIGATION_LOG)."""
    if path is None:
        path = os.environ.get("GLUTEN_INVESTIGATION_LOG") or str(
            Path("data") / "investigation_memory.jsonl"
        )
    return InvestigationOrchestrator(memory=ProvenanceMemory(path))


__all__ = [
    "NON_CLAIMS",
    "Hypothesis",
    "Scenario",
    "InvestigationOrchestrator",
    "get_orchestrator",
]
