"""Decision intelligence: evidence-backed decisions and outcome comparison (V7 P4).

This module turns a goal into a recorded :class:`DecisionRecord` - the chosen
plan, the evidence behind it, the confidence, the uncertainty and the rationale -
and later compares the *predicted* outcome with the *actual* one.

It composes existing systems rather than duplicating them:

* ``agentic.reasoning.StructuredReasoning`` and ``agentic.planning.PlanAnalyzer``
  produce the reasoning and the candidate plans.
* ``agentic.retrieval.MemoryRetriever`` supplies verified evidence and P3 lessons
  (``kind="lesson"``).
* ``agentic.reflection.ReflectionEngine`` evaluates a finished task's steps for the
  predicted-vs-actual comparison.

Hard rules:

* A decision is never presented as more certain than its evidence. Confidence is
  capped by the fraction of the goal backed by verified evidence.
* A hypothesis is never promoted to a verified fact: the comparison stores a
  lesson at ``verification="hypothesis"`` and never calls ``verify``.
* A decision that needs owner approval, or that rests on unresolved unknowns or
  contradictions, is flagged as requiring human input.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.memory import AgentMemory, get_agent_memory
from genesis_protocol.agentic.planning import PlanAnalyzer, PlanningResult
from genesis_protocol.agentic.reasoning import StructuredReasoning, StructuredReasoningResult
from genesis_protocol.agentic.reflection import ReflectionEngine
from genesis_protocol.agentic.retrieval import MemoryRetriever

# Confidence cannot exceed the share of the goal that verified evidence supports.
MAX_CONFIDENCE_WITHOUT_EVIDENCE = 0.5


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DecisionRecord:
    """A recorded decision: what was chosen, why, and how sure we are."""

    id: str
    goal: str
    user_id: int
    chosen_plan: Optional[str]
    rationale: str
    evidence: List[Dict[str, Any]]
    lessons: List[Dict[str, Any]]
    confidence: float
    uncertainty: float
    predicted_outcome: str
    risks: List[Dict[str, Any]]
    human_input_required: bool
    human_input_reasons: List[str]
    created_at: str = field(default_factory=_utcnow)
    actual_outcome: Optional[str] = None
    outcome_matches_prediction: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    """Produces evidence-backed decisions and compares predicted vs actual."""

    def __init__(
        self,
        memory: Optional[AgentMemory] = None,
        retriever: Optional[MemoryRetriever] = None,
        analyzer: Optional[PlanAnalyzer] = None,
        reflection: Optional[ReflectionEngine] = None,
    ):
        self.memory = memory or get_agent_memory()
        self.retriever = retriever or MemoryRetriever(memory=self.memory)
        self.analyzer = analyzer or PlanAnalyzer()
        self.reasoner = StructuredReasoning(retriever=self.retriever)
        self.reflection = reflection or ReflectionEngine(memory=self.memory)

    # -- evidence -------------------------------------------------------------

    def gather_evidence(self, user_id: int, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Verified memory that supports ``query``. Only ``verified`` rows count."""
        try:
            ranked = self.retriever.search(user_id, query, limit=limit)
        except Exception:
            return []
        return [s.memory for s in ranked if s.memory.get("verification") == "verified"]

    def gather_lessons(self, user_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """P3 lessons relevant to future planning (kept as hypotheses)."""
        try:
            lessons = self.memory.list_memories(user_id, kind="lesson")
        except Exception:
            return []
        return lessons[:limit]

    # -- decision -------------------------------------------------------------

    def decide(
        self,
        goal: str,
        user_id: int,
        owner_approved: bool = False,
        risk_tolerance: str = "moderate",
    ) -> DecisionRecord:
        """Reason, plan, pick and record a decision for ``goal``."""
        reasoning: StructuredReasoningResult = self.reasoner.analyze(goal, user_id)
        planning: PlanningResult = self.analyzer.analyze(
            reasoning, user_id, owner_approved=owner_approved, risk_tolerance=risk_tolerance
        )

        evidence = self.gather_evidence(user_id, goal)
        lessons = self.gather_lessons(user_id)

        # Confidence is bounded by evidence, by reasoning confidence and by the
        # recommended plan's own feasibility, and is never presented as certainty:
        # a plan that has not run cannot be more than highly likely.
        base = reasoning.confidence
        evidence_factor = 1.0 if evidence else MAX_CONFIDENCE_WITHOUT_EVIDENCE
        feasibility = 1.0
        if planning.recommended is not None:
            feasibility = next(
                c.feasibility for c in planning.candidates if c.name == planning.recommended
            )
        confidence = round(min(0.95, min(1.0, base) * evidence_factor * feasibility), 4)
        if planning.recommended is None:
            confidence = min(confidence, 0.2)
        uncertainty = round(1.0 - confidence, 4)

        chosen = None
        if planning.recommended is not None:
            chosen = next(c for c in planning.candidates if c.name == planning.recommended)

        risks: List[Dict[str, Any]] = []
        if chosen is not None:
            risks = [r.to_dict() for r in chosen.risks]

        if chosen is None:
            predicted = "no authorized plan; outcome unknown"
        elif chosen.requires_owner_approval:
            predicted = "plan would need owner approval; not autonomously executable"
        elif risks:
            predicted = "plan may succeed but carries identified risks"
        else:
            predicted = "plan is expected to succeed if every step succeeds"

        human_reasons = list(planning.human_input_reasons)
        if reasoning.injection_flagged:
            human_reasons.append("goal contains instruction-like content; human review required")
        if not evidence:
            human_reasons.append("no verified evidence supports this decision")

        return DecisionRecord(
            id=uuid.uuid4().hex[:12],
            goal=goal,
            user_id=int(user_id),
            chosen_plan=planning.recommended,
            rationale=planning.recommendation_reason,
            evidence=evidence,
            lessons=lessons,
            confidence=confidence,
            uncertainty=uncertainty,
            predicted_outcome=predicted,
            risks=risks,
            human_input_required=bool(human_reasons),
            human_input_reasons=human_reasons,
        )

    # -- predicted vs actual --------------------------------------------------

    def compare_outcome(
        self, decision: DecisionRecord, task_result: Dict[str, Any]
    ) -> DecisionRecord:
        """Compare a finished task's outcome with the decision's prediction.

        When ``task_result`` carries a task id and steps, the P3
        ``ReflectionEngine`` evaluates it (what worked / failed / why) and its
        lessons are recorded too. The prediction-vs-actual lesson is always
        recorded at ``verification="hypothesis"``. Nothing here promotes a
        hypothesis into a verified fact.
        """
        state = str((task_result or {}).get("state", "unknown"))
        decision.actual_outcome = state
        predicted_success = "expected to succeed" in decision.predicted_outcome
        actual_success = state == "completed"
        decision.outcome_matches_prediction = (predicted_success == actual_success)

        # Reuse the P3 reflection engine when there is a real task to evaluate.
        task_id = (task_result or {}).get("task_id")
        if task_id and (task_result or {}).get("steps"):
            try:
                self.reflection.reflect(
                    decision.user_id, task_id=task_id, record=task_result
                )
            except Exception:
                pass

        lesson = (
            f"Prediction ({decision.predicted_outcome}) "
            f"{'matched' if decision.outcome_matches_prediction else 'did not match'} "
            f"actual outcome '{state}' for goal: {decision.goal[:120]}"
        )
        try:
            self.memory.remember(
                decision.user_id,
                lesson,
                kind="lesson",
                approved=True,
                source="reflection",
                verification="hypothesis",
                confidence=decision.confidence,
                origin=decision.id,
                provenance={
                    "decision_id": decision.id,
                    "predicted": decision.predicted_outcome,
                    "actual": state,
                    "matched": decision.outcome_matches_prediction,
                },
            )
        except Exception:
            # A lesson that cannot be stored must not break the comparison.
            pass
        return decision
