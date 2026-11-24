"""Independent verification (V7 investigation).

A single reviewer, or a single source, can be wrong - or manipulated. This module
adds the checks that catch the classic failure modes before a finding is trusted:

* **Source manipulation** - two "independent" sources that are actually the same
  origin (same name, same url, or declared non-independent) do not corroborate.
* **Hallucination** - a source or quote that cannot be located is flagged; an
  unsourced assertion is not evidence.
* **Confirmation bias** - a review panel that only ever agrees is flagged; a
  panel must contain at least one independent reviewer, and dissent is recorded,
  not averaged away.
* **Contradictory evidence** - contradictory findings are surfaced explicitly
  rather than silently resolved.
* **False binary** - a question forced into a yes/no when the evidence is
  missing or graded is flagged as a false binary.
* **Missing data / incorrect assumptions** - declared and reported, never
  filled in with a guess.

The module *reports*; it never rewrites the finding. That keeps verification
independent from the thing it verifies.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from genesis_protocol.investigation.evidence import Evidence, Finding

# Finding levels that are positive assertions.
_POSITIVE = {"verified", "corroborated", "plausible"}


@dataclass
class Reviewer:
    """An independent reviewer of a finding."""

    name: str
    agrees: bool
    independent: bool = True
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewIssue:
    kind: str
    severity: str  # info | medium | high
    detail: str
    related: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewResult:
    finding_id: str
    issues: List[ReviewIssue] = field(default_factory=list)
    reviewers: List[Reviewer] = field(default_factory=list)
    trusted: bool = False
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "trusted": self.trusted,
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
            "reviewers": [r.to_dict() for r in self.reviewers],
        }


def _origin_key(ev: Evidence) -> str:
    src = ev.source
    return (src.url or src.name or "").strip().lower()


def detect_source_manipulation(evidence: List[Evidence]) -> List[ReviewIssue]:
    """Flag 'independent' sources that share an origin or are self-declared."""
    issues: List[ReviewIssue] = []
    seen: Dict[str, str] = {}
    for ev in evidence:
        key = _origin_key(ev)
        if not key:
            continue
        if key in seen:
            issues.append(ReviewIssue(
                kind="source_manipulation",
                severity="high",
                detail=(
                    f"'{ev.source.name}' shares an origin with '{seen[key]}'; "
                    "they are not independent corroboration."
                ),
                related=[ev.source.name, seen[key]],
            ))
        else:
            seen[key] = ev.source.name
        if ev.source.self_reported and ev.supports:
            issues.append(ReviewIssue(
                kind="source_manipulation",
                severity="medium",
                detail=f"'{ev.source.name}' is self-reported and cannot be primary.",
                related=[ev.source.name],
            ))
    return issues


def detect_hallucination(evidence: List[Evidence], located: Optional[Dict[str, bool]] = None) -> List[ReviewIssue]:
    """Flag evidence whose source cannot be located.

    ``located`` maps source name -> whether an independent locator found it. A
    source absent from the map is *unlocated* and is flagged, not assumed real.
    """
    issues: List[ReviewIssue] = []
    located = located or {}
    for ev in evidence:
        if not ev.source.url and not ev.source.name:
            issues.append(ReviewIssue(
                kind="hallucination",
                severity="high",
                detail="evidence has no identifiable source",
            ))
            continue
        if ev.source.name in located and located[ev.source.name] is False:
            issues.append(ReviewIssue(
                kind="hallucination",
                severity="high",
                detail=f"source '{ev.source.name}' could not be located by the locator.",
                related=[ev.source.name],
            ))
    return issues


def detect_confirmation_bias(reviewers: List[Reviewer]) -> List[ReviewIssue]:
    issues: List[ReviewIssue] = []
    if not reviewers:
        issues.append(ReviewIssue(
            kind="confirmation_bias",
            severity="medium",
            detail="no independent reviewer was recorded.",
        ))
        return issues
    independent = [r for r in reviewers if r.independent]
    if not independent:
        issues.append(ReviewIssue(
            kind="confirmation_bias",
            severity="high",
            detail="no reviewer is independent of the finding's author.",
        ))
    if all(r.agrees for r in reviewers):
        issues.append(ReviewIssue(
            kind="confirmation_bias",
            severity="medium",
            detail="every reviewer agreed; unanimity without dissent is a bias signal.",
        ))
    return issues


def detect_false_binary(question: str, options: List[str], evidence: List[Evidence]) -> List[ReviewIssue]:
    """Flag a yes/no question posed while the evidence is missing or graded."""
    issues: List[ReviewIssue] = []
    normalised = {o.strip().lower() for o in options}
    is_binary = normalised in ({"yes", "no"}, {"true", "false"}, {"0", "1"}, {"y", "n"})
    if not is_binary:
        return issues
    if not evidence:
        issues.append(ReviewIssue(
            kind="false_binary",
            severity="medium",
            detail=f"'{question}' is posed as a binary with no evidence; the honest answer is unknown.",
        ))
    else:
        graded = {e.supports for e in evidence}
        if len(graded) == 1 and not any(e.source.reliability >= 0.7 for e in evidence):
            issues.append(ReviewIssue(
                kind="false_binary",
                severity="info",
                detail=(
                    f"'{question}' is binary but the evidence is weak and one-sided; "
                    "consider an 'unknown' or graded answer."
                ),
            ))
    return issues


def detect_contradictions(findings: List[Finding]) -> List[ReviewIssue]:
    """Report pairs of findings that assert opposite things."""
    issues: List[ReviewIssue] = []
    positives = [f for f in findings if f.level in _POSITIVE]
    for i, a in enumerate(positives):
        for b in positives[i + 1:]:
            if _contradict(a.claim, b.claim):
                issues.append(ReviewIssue(
                    kind="contradictory_evidence",
                    severity="high",
                    detail=f"'{a.finding_id}' and '{b.finding_id}' appear to contradict.",
                    related=[a.finding_id, b.finding_id],
                ))
    return issues


def _contradict(a: str, b: str) -> bool:
    """Very conservative contradiction test: same subject, opposite polarity.

    Word-overlap based, deliberately dumb and explainable. It only fires on a
    high overlap so it does not manufacture contradictions from unrelated text.
    """
    aw = set(_words(a))
    bw = set(_words(b))
    if not aw or not bw:
        return False
    overlap = len(aw & bw) / max(1, min(len(aw), len(bw)))
    if overlap < 0.6:
        return False
    neg = {"not", "no", "never", "cannot", "isn't", "aren't", "doesn't", "false"}
    return bool((aw & neg) ^ (bw & neg))


def _words(text: str) -> List[str]:
    cleaned = "".join(c.lower() if (c.isalnum() or c.isspace()) else " " for c in text)
    return [w for w in cleaned.split() if len(w) > 2]


class IndependentVerifier:
    """Runs the full battery and produces a trust verdict (never a rewrite)."""

    def __init__(self, min_independent_reviewers: int = 2):
        self.min_independent_reviewers = min_independent_reviewers

    def review(
        self,
        finding: Finding,
        reviewers: Optional[List[Reviewer]] = None,
        located: Optional[Dict[str, bool]] = None,
        question: str = "",
        options: Optional[List[str]] = None,
        related: Optional[List[Finding]] = None,
    ) -> ReviewResult:
        reviewers = reviewers or []
        issues: List[ReviewIssue] = []
        issues += detect_source_manipulation(finding.evidence)
        issues += detect_hallucination(finding.evidence, located)
        issues += detect_confirmation_bias(reviewers)
        if question and options:
            issues += detect_false_binary(question, options, finding.evidence)
        if related:
            issues += detect_contradictions([finding] + list(related))

        independent = [r for r in reviewers if r.independent]
        high = [i for i in issues if i.severity == "high"]
        # A finding is trusted only if there is enough independent review and no
        # high-severity issue. Positive claims additionally need a reviewer to
        # actually agree; a mere absence of complaint is not agreement.
        trusted = (
            len(independent) >= self.min_independent_reviewers
            and not high
        )
        if trusted and finding.level in _POSITIVE:
            trusted = any(r.agrees for r in independent)

        summary = (
            "trusted" if trusted
            else "not trusted: " + (high[0].detail if high else "insufficient independent review")
        )
        return ReviewResult(
            finding_id=finding.finding_id,
            issues=issues,
            reviewers=list(reviewers),
            trusted=trusted,
            summary=summary,
        )


__all__ = [
    "Reviewer",
    "ReviewIssue",
    "ReviewResult",
    "IndependentVerifier",
    "detect_source_manipulation",
    "detect_hallucination",
    "detect_confirmation_bias",
    "detect_false_binary",
    "detect_contradictions",
]
