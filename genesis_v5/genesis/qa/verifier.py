"""Independent QA verifier.

The verifier is deliberately independent of the agent that produced the
result: it never trusts the producer's own assessment. It scores results,
detects contradictions between outputs, and escalates failures.

Offline, deterministic heuristics keep it testable without a model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from genesis.reflection.reflection import ReflectionEngine


@dataclass
class VerifierConfig:
    max_correction_iterations: int = 3
    pass_threshold: float = 0.6
    require_evidence: bool = True


@dataclass
class VerificationOutcome:
    task: str
    passed: bool
    score: float
    confidence: float
    issues: list[str] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    iterations: int = 1
    escalated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "passed": self.passed,
            "score": self.score,
            "confidence": self.confidence,
            "issues": list(self.issues),
            "contradictions": list(self.contradictions),
            "iterations": self.iterations,
            "escalated": self.escalated,
        }


_FAIL_MARKERS = re.compile(r"(?i)\b(error|failed|failure|exception|traceback)\b")
_POSITIVE = re.compile(r"(?i)\b(pass|success|ok|complete|valid|correct|verified)\b")
_NEGATIVE = re.compile(r"(?i)\b(fail|invalid|incorrect|broken|wrong)\b")


class IndependentVerifier:
    def __init__(
        self,
        config: VerifierConfig | None = None,
        reflection: ReflectionEngine | None = None,
    ) -> None:
        self.config = config or VerifierConfig()
        self.reflection = reflection or ReflectionEngine()

    # ------------------------------------------------------------------
    def verify(
        self,
        *,
        task: str,
        result: Any,
        expected: str | None = None,
        producer_claim: bool | None = None,
        prior_iterations: int = 0,
    ) -> VerificationOutcome:
        """Score a result independently of its producer.

        `producer_claim` is the producer's own assessment — it is treated as
        untrusted and only used to detect overconfidence.
        """
        text = str(result)
        issues: list[str] = []

        # 1. Completeness — an empty result is always a hard failure.
        if not text.strip():
            issues.append("empty result")
        completeness = 0.0 if not text.strip() else min(1.0, len(text) / 120.0)

        # 2. Failure markers
        has_failure = bool(_FAIL_MARKERS.search(text))
        if has_failure:
            issues.append("result contains failure markers")

        # 3. Expected content (ground truth), when available
        consistency = 1.0
        if expected is not None and expected.strip():
            consistency = 1.0 if expected.strip() in text else 0.3
            if consistency < 1.0:
                issues.append("result missing expected content")

        # 4. Producer overconfidence detection
        if producer_claim is True and has_failure:
            issues.append("producer claimed success despite failure markers")

        if not text.strip():
            passed = False
            score = 0.0
        else:
            score = (
                completeness * 0.4
                + consistency * 0.4
                + (0.2 if not has_failure else 0.0)
            )
            score = max(0.0, min(1.0, score))
            passed = score >= self.config.pass_threshold and not has_failure

        confidence = score
        if producer_claim is True and has_failure:
            confidence = min(confidence, 0.2)

        return VerificationOutcome(
            task=task,
            passed=passed,
            score=round(score, 3),
            confidence=round(confidence, 3),
            issues=issues,
            iterations=prior_iterations + 1,
        )

    # ------------------------------------------------------------------
    def check_contradictions(
        self,
        *,
        task: str,
        outputs: list[tuple[str, Any]],
    ) -> VerificationOutcome:
        """Detect contradictions across multiple agent outputs."""
        outcome = VerificationOutcome(task=task, passed=True, score=1.0, confidence=1.0)
        for i in range(len(outputs)):
            for j in range(i + 1, len(outputs)):
                id_a, out_a = outputs[i]
                id_b, out_b = outputs[j]
                contradiction = self.reflection.compare(
                    pair_repr=f"{id_a} vs {id_b}",
                    a=out_a,
                    b=out_b,
                    result_a_id=id_a,
                    result_b_id=id_b,
                )
                if contradiction is not None:
                    outcome.contradictions.append(contradiction.to_dict())
                    if contradiction.severity == "error":
                        outcome.passed = False
                        outcome.score = min(outcome.score, 0.3)
        if outcome.contradictions:
            outcome.issues.append(
                f"{len(outcome.contradictions)} contradiction(s) detected"
            )
        return outcome

    # ------------------------------------------------------------------
    def bounded_correction_loop(
        self,
        *,
        task: str,
        result: Any,
        expected: str | None = None,
        correct_fn=None,
        max_iterations: int | None = None,
    ) -> VerificationOutcome:
        """Bounded correction loop: verify -> correct -> re-verify.

        `correct_fn(result, iteration) -> corrected_result`. The loop is
        bounded by max_iterations; escalation is triggered when the bound is
        hit without passing.
        """
        limit = max_iterations or self.config.max_correction_iterations
        current = result
        outcome: VerificationOutcome | None = None
        for iteration in range(limit):
            outcome = self.verify(
                task=task, result=current, expected=expected,
                prior_iterations=iteration,
            )
            if outcome.passed:
                return outcome
            if correct_fn is None:
                break
            current = correct_fn(current, iteration)
        assert outcome is not None
        outcome.escalated = True
        outcome.issues.append("correction bound reached; escalated")
        return outcome

    # ------------------------------------------------------------------
    def verify_team(
        self,
        *,
        task: str,
        results: list[dict[str, Any]],
        expected: str | None = None,
    ) -> VerificationOutcome:
        """Verify a team's aggregated result with contradiction detection."""
        outputs = [
            (str(r.get("agent", "?")), r.get("output", ""))
            for r in results
        ]
        combined = " ".join(str(o) for _, o in outputs)
        outcome = self.verify(task=task, result=combined, expected=expected)
        contradiction_check = self.check_contradictions(task=task, outputs=outputs)
        outcome.contradictions = contradiction_check.contradictions
        if not contradiction_check.passed:
            outcome.passed = False
            outcome.score = min(outcome.score, contradiction_check.score)
            outcome.issues.extend(contradiction_check.issues)
        return outcome