"""Time-loop-inspired feedback engine (V7 investigation).

An engineering equivalent of a "time loop": record -> predict -> act (only what
is permitted) -> compare -> detect error -> propose correction -> test in
isolation -> keep history and enable rollback.

The loop never rewrites history and never fabricates an outcome. Every stage
writes to the provenance memory, and the actual outcome is whatever the caller
*actually observed* - it is never inferred or invented. Corrections are
proposals tested in isolation; they are not applied to production here.

The loop is also a guard against its own worst failure mode: a "correction" that
is really a cover-up. If the recorded prediction and the observed outcome
disagree, that disagreement is preserved and surfaced, not smoothed over.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from genesis_protocol.investigation.provenance import Provenance, ProvenanceMemory


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Prediction:
    """A forecast made *before* acting, with its confidence."""

    predicted: Any
    confidence: float = 0.5
    rationale: str = ""

    def __post_init__(self) -> None:
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Cycle:
    """One full turn of the loop, from input to correction proposal."""

    cycle_id: str
    input: Any
    context: Dict[str, Any] = field(default_factory=dict)
    decision: str = ""
    prediction: Optional[Prediction] = None
    actual: Any = None
    matched: Optional[bool] = None
    error: str = ""
    correction: Optional[Dict[str, Any]] = None
    correction_tested: bool = False
    correction_safe: bool = False
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["prediction"] = self.prediction.to_dict() if self.prediction else None
        return data


def _compare(predicted: Any, actual: Any) -> bool:
    """Compare prediction to actual. Conservative: unknown shape -> mismatch."""
    if isinstance(predicted, dict) and isinstance(actual, dict):
        keys = set(predicted) | set(actual)
        return all(predicted.get(k) == actual.get(k) for k in keys)
    return predicted == actual


class FeedbackEngine:
    """Runs the record/predict/act/compare/correct/test loop.

    ``memory`` is the provenance store; if omitted an in-memory one is created.
    ``permit`` is the permission check applied *before* any action runs; the
    default refuses everything (fail closed) so a caller must opt in explicitly.
    """

    def __init__(
        self,
        memory: Optional[ProvenanceMemory] = None,
        permit: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ):
        self.memory = memory or ProvenanceMemory()
        self._permit = permit or (lambda _decision, _ctx: False)
        self._cycles: Dict[str, Cycle] = {}
        self._counter = 0

    # -- 1. record -----------------------------------------------------------
    def begin(self, input: Any, context: Optional[Dict[str, Any]] = None) -> Cycle:
        self._counter += 1
        cid = f"cycle-{self._counter:04d}"
        cycle = Cycle(cycle_id=cid, input=input, context=dict(context or {}))
        self._cycles[cid] = cycle
        self.memory.append("cycle.input", {"cycle_id": cid, "input": input,
                                           "context": cycle.context},
                           Provenance(actor="feedback-engine", method="record"))
        return cycle

    # -- 2. predict ----------------------------------------------------------
    def predict(self, cycle: Cycle, predicted: Any, confidence: float = 0.5,
                rationale: str = "") -> Prediction:
        cycle.prediction = Prediction(predicted, confidence, rationale)
        cycle.updated_at = utcnow()
        self.memory.append("cycle.prediction",
                           {"cycle_id": cycle.cycle_id, "predicted": predicted,
                            "confidence": cycle.prediction.confidence},
                           Provenance(actor="feedback-engine", method="predict"))
        return cycle.prediction

    # -- 3. act (only if permitted) -----------------------------------------
    def act(self, cycle: Cycle, decision: str, action: Callable[[], Any]) -> Dict[str, Any]:
        """Run ``action`` only if the permission check allows it.

        Returns a record. A refused action is *not* run, and that refusal is
        recorded - it is a real outcome, not a missing one.
        """
        cycle.decision = decision
        allowed = bool(self._permit(decision, cycle.context))
        self.memory.append(
            "cycle.decision",
            {"cycle_id": cycle.cycle_id, "decision": decision, "permitted": allowed},
            Provenance(actor="feedback-engine", method="act"),
        )
        if not allowed:
            cycle.actual = {"refused": True, "decision": decision}
            cycle.updated_at = utcnow()
            return {"permitted": False, "actual": cycle.actual}
        actual = action()
        cycle.actual = actual
        cycle.updated_at = utcnow()
        return {"permitted": True, "actual": actual}

    # -- 4. compare ----------------------------------------------------------
    def compare(self, cycle: Cycle) -> bool:
        if cycle.prediction is None:
            raise ValueError("cannot compare without a prediction")
        cycle.matched = _compare(cycle.prediction.predicted, cycle.actual)
        cycle.updated_at = utcnow()
        self.memory.append(
            "cycle.comparison",
            {"cycle_id": cycle.cycle_id, "predicted": cycle.prediction.predicted,
             "actual": cycle.actual, "matched": cycle.matched},
            Provenance(actor="feedback-engine", method="compare"),
        )
        return cycle.matched

    # -- 5. detect error -----------------------------------------------------
    def detect_error(self, cycle: Cycle) -> str:
        if cycle.matched is None:
            cycle.error = "comparison not run"
        elif cycle.matched:
            cycle.error = ""
        else:
            cycle.error = (
                f"prediction {cycle.prediction.predicted!r} did not match "
                f"actual {cycle.actual!r}"
            )
        cycle.updated_at = utcnow()
        if cycle.error:
            self.memory.append("cycle.error",
                               {"cycle_id": cycle.cycle_id, "error": cycle.error},
                               Provenance(actor="feedback-engine", method="detect"))
        return cycle.error

    # -- 6. propose correction ----------------------------------------------
    def propose_correction(self, cycle: Cycle, proposal: Dict[str, Any]) -> Dict[str, Any]:
        proposal = dict(proposal or {})
        proposal.setdefault("cycle_id", cycle.cycle_id)
        proposal.setdefault("based_on_error", cycle.error)
        cycle.correction = proposal
        cycle.updated_at = utcnow()
        self.memory.append("cycle.correction",
                           {"cycle_id": cycle.cycle_id, "proposal": proposal},
                           Provenance(actor="feedback-engine", method="correct"))
        return proposal

    # -- 7. test correction in isolation ------------------------------------
    def test_correction(
        self,
        cycle: Cycle,
        tester: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Dict[str, Any]:
        """Test a proposed correction in isolation.

        ``tester`` must return a mapping with ``safe`` (bool). If no tester is
        supplied, the correction is treated as **unsafe** (fail closed) - an
        untested correction must never be applied.
        """
        if cycle.correction is None:
            raise ValueError("no correction to test")
        if tester is None:
            cycle.correction_tested = True
            cycle.correction_safe = False
        else:
            result = tester(cycle.correction) or {}
            cycle.correction_tested = True
            cycle.correction_safe = bool(result.get("safe", False))
        cycle.updated_at = utcnow()
        self.memory.append(
            "cycle.correction_test",
            {"cycle_id": cycle.cycle_id, "tested": cycle.correction_tested,
             "safe": cycle.correction_safe},
            Provenance(actor="feedback-engine", method="test"),
        )
        return {"tested": cycle.correction_tested, "safe": cycle.correction_safe}

    # -- 8. history / rollback ----------------------------------------------
    def history(self, cycle_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if cycle_id is None:
            return self.memory.export()
        return [e for e in self.memory.export()
                if e.get("payload", {}).get("cycle_id") == cycle_id]

    def snapshot(self, cycle: Cycle) -> str:
        """A stable digest of a cycle's recorded state, for rollback checks."""
        return hashlib.sha256(
            str(sorted(cycle.to_dict().items(), key=lambda kv: kv[0])).encode("utf-8")
        ).hexdigest()

    def rollback(self, cycle_id: str, reason: str) -> Dict[str, Any]:
        """Mark a cycle rolled back. History is preserved; nothing is deleted."""
        if cycle_id not in self._cycles:
            raise KeyError(f"unknown cycle '{cycle_id}'")
        self.memory.append("cycle.rollback",
                           {"cycle_id": cycle_id, "reason": reason},
                           Provenance(actor="feedback-engine", method="rollback"))
        return {"rolled_back": cycle_id, "reason": reason}

    def cycle(self, cycle_id: str) -> Optional[Cycle]:
        return self._cycles.get(cycle_id)


__all__ = ["Prediction", "Cycle", "FeedbackEngine"]
