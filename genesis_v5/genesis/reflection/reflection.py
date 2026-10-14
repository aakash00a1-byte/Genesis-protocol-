"""Reflection engine: bounded reflection over agent results.

Reflection is bounded (max_iterations) and never marks results as
unquestionably correct — it produces confidence metadata, contradiction
signals, and quality scores that downstream verification (Phase 8) uses.
Dependency-free heuristic implementation so it runs fully offline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Contradiction:
    result_a_id: str
    result_b_id: str
    reason: str
    severity: str = "warning"  # warning | error

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_a_id": self.result_a_id,
            "result_b_id": self.result_b_id,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass
class QualityScore:
    completeness: float = 1.0
    consistency: float = 1.0
    evidence: float = 1.0
    overall: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "completeness": self.completeness,
            "consistency": self.consistency,
            "evidence": self.evidence,
            "overall": self.overall,
        }


@dataclass
class ReflectionResult:
    agent: str
    task_id: str
    passed: bool
    confidence: float
    quality: QualityScore = field(default_factory=QualityScore)
    contradictions: list[Contradiction] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    iterations: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "task_id": self.task_id,
            "passed": self.passed,
            "confidence": self.confidence,
            "quality": self.quality.to_dict(),
            "contradictions": [c.to_dict() for c in self.contradictions],
            "issues": list(self.issues),
            "iterations": self.iterations,
        }


_EXPECTED_MARKERS = [
    re.compile(r"(?i)ERROR"),
    re.compile(r"(?i)FAIL(ED|URE)?"),
    re.compile(r"(?i)TRACEBACK"),
    re.compile(r"(?i)EXCEPTION"),
]

# Positive/negative sentiment for coarse consistency heuristic.
POSITIVE = re.compile(r"(?i)\b(pass(es|ed)?|success|ok|complete|valid|correct)\b")
NEGATIVE = re.compile(r"(?i)\b(fail(ed)?|error|invalid|incorrect|broken)\b")


class ReflectionEngine:
    def __init__(self, max_iterations: int = 3) -> None:
        self.max_iterations = max_iterations

    def reflect(
        self,
        *,
        agent: str,
        task_id: str,
        result_output: Any,
        expected: str | None = None,
        prior_iterations: int = 0,
    ) -> ReflectionResult:
        """Reflect on a single agent result."""
        iterations = prior_iterations + 1
        output_text = str(result_output)
        issues: list[str] = []

        completeness = 1.0
        if not output_text.strip():
            completeness = 0.0
            issues.append("empty output")

        # Failure markers reduce confidence.
        failure_markers = sum(
            1 for m in _EXPECTED_MARKERS if m.search(output_text)
        )
        has_failure = failure_markers > 0
        if has_failure:
            issues.append("output contains failure markers")

        # Consistency with expected ground truth (when provided).
        consistency = 1.0
        if expected is not None:
            if expected.strip() and expected.strip() not in output_text:
                consistency = 0.4
                issues.append("output missing expected content")

        # Evidence heuristic: length + detail.
        evidence = min(1.0, len(output_text) / 200.0)

        overall = (completeness * 0.4 + consistency * 0.4 + evidence * 0.2)
        overall = max(0.0, min(1.0, overall))

        passed = overall >= 0.6 and not has_failure
        confidence = overall

        return ReflectionResult(
            agent=agent,
            task_id=task_id,
            passed=passed,
            confidence=round(confidence, 3),
            quality=QualityScore(
                completeness=round(completeness, 3),
                consistency=round(consistency, 3),
                evidence=round(evidence, 3),
                overall=round(overall, 3),
            ),
            contradictions=[],
            issues=issues,
            iterations=iterations,
        )

    def compare(
        self,
        *,
        pair_repr: str,
        a: Any,
        b: Any,
        result_a_id: str,
        result_b_id: str,
    ) -> Contradiction | None:
        """Detect contradictions between two outputs.

        Contradiction when one output is positive/complete and the other is
        negative, or when outputs differ materially in normalized form.
        """
        text_a = str(a).strip().lower()
        text_b = str(b).strip().lower()
        if not text_a or not text_b:
            return None
        if text_a == text_b:
            return None

        a_pos = bool(POSITIVE.search(text_a)) and not NEGATIVE.search(text_a)
        b_pos = bool(POSITIVE.search(text_b)) and not NEGATIVE.search(text_b)
        a_neg = bool(NEGATIVE.search(text_a)) and not POSITIVE.search(text_a)
        b_neg = bool(NEGATIVE.search(text_b)) and not POSITIVE.search(text_b)

        if (a_pos and b_neg) or (a_neg and b_pos):
            return Contradiction(
                result_a_id=result_a_id,
                result_b_id=result_b_id,
                reason=f"contradictory sentiment between outputs ({pair_repr})",
                severity="error",
            )
        if abs(len(text_a) - len(text_b)) > 100:
            return Contradiction(
                result_a_id=result_a_id,
                result_b_id=result_b_id,
                reason=f"material length divergence ({pair_repr})",
                severity="warning",
            )
        return None

    def bounded_correction(
        self,
        *,
        agent: str,
        task_id: str,
        current_output: Any,
        expected: str | None = None,
        max_iterations: int | None = None,
        correct_fn=None,
    ) -> ReflectionResult:
        """Bounded correction loop: improves the output up to max_iterations.

        `correct_fn` (optional) applies a correction to the output and is
        bounded to the iteration cap. Without it, the loop only reflects.
        """
        limit = max_iterations or self.max_iterations
        current = current_output
        for iteration in range(limit):
            outcome = self.reflect(
                agent=agent,
                task_id=task_id,
                result_output=current,
                expected=expected,
                prior_iterations=iteration,
            )
            if outcome.passed:
                return outcome
            if correct_fn is None:
                return outcome
            current = correct_fn(current, iteration)
        # Final reflect after last correction.
        return self.reflect(
            agent=agent,
            task_id=task_id,
            result_output=current,
            expected=expected,
            prior_iterations=limit,
        )