"""Evidence classification (V7 investigation).

Every finding is classified into exactly one of six levels. The classification
is a *rule*, not an opinion: it is derived from the evidence attached to the
finding, so the same evidence always yields the same level and a reviewer can
re-derive it by hand.

Levels (ordered, weakest to strongest):

* ``VERIFIED``     - supported by a reliable **primary** source.
* ``CORROBORATED`` - supported independently by multiple credible sources.
* ``PLAUSIBLE``    - technically possible, not demonstrated.
* ``SPECULATIVE``  - hypothesis without sufficient evidence.
* ``FALSE``        - contradicted by reliable evidence.
* ``UNKNOWN``      - insufficient information.

Two hard rules, both enforced here:

1. **Never promote speculation to verified.** ``VERIFIED`` requires at least one
   reliable primary source, and a finding contradicted by reliable evidence can
   never rise above ``FALSE``. ``promote`` refuses any upward move that the
   evidence does not support.
2. **Sources are never trusted blindly.** A source's reliability is an explicit
   property of the source, and self-reported or anonymous sources are not
   primary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List

VERIFIED = "verified"
CORROBORATED = "corroborated"
PLAUSIBLE = "plausible"
SPECULATIVE = "speculative"
FALSE = "false"
UNKNOWN = "unknown"

# Strength order used to decide whether a promotion is allowed. ``FALSE`` is
# deliberately below every positive level: evidence that contradicts a finding
# keeps it false no matter how many sources assert it.
LEVEL_ORDER = [FALSE, UNKNOWN, SPECULATIVE, PLAUSIBLE, CORROBORATED, VERIFIED]

LEVEL_LABELS = {
    VERIFIED: "Supported by reliable primary evidence",
    CORROBORATED: "Independently supported by multiple credible sources",
    PLAUSIBLE: "Technically possible, not demonstrated",
    SPECULATIVE: "Hypothesis without sufficient evidence",
    FALSE: "Contradicted by reliable evidence",
    UNKNOWN: "Insufficient information",
}

# Source kinds, strongest to weakest. Only ``primary`` and ``official`` count as
# primary evidence for VERIFIED.
PRIMARY_KINDS = ("primary", "official")
CREDIBLE_KINDS = ("primary", "official", "credible")


class EvidenceError(ValueError):
    """Raised when a classification or promotion is not evidence-supported."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Source:
    """Where a piece of evidence came from.

    ``reliability`` is an explicit, auditable property (0..1). It is not a
    statement about the claim - only about the source. ``kind`` says what the
    source *is*; only ``primary``/``official`` sources count as primary.
    """

    name: str
    kind: str = "unknown"  # primary | official | credible | secondary | anonymous | unknown
    reliability: float = 0.0
    url: str = ""
    independent: bool = True
    self_reported: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        self.reliability = max(0.0, min(1.0, float(self.reliability)))
        if self.self_reported and self.kind in PRIMARY_KINDS:
            # A source cannot be primary *and* self-reported; self-report is the
            # weakest form of evidence, whatever the publisher calls itself.
            self.kind = "secondary"

    @property
    def is_primary(self) -> bool:
        return self.kind in PRIMARY_KINDS and not self.self_reported

    @property
    def is_credible(self) -> bool:
        return self.kind in CREDIBLE_KINDS and not self.self_reported

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Evidence:
    """One piece of evidence for or against a claim."""

    source: Source
    claim: str
    supports: bool = True  # False = this evidence *contradicts* the claim
    detail: str = ""
    recorded_at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.to_dict()
        return data


def _independent_sources(evidence: List[Evidence], supporting: bool) -> List[Source]:
    seen: List[Source] = []
    for ev in evidence:
        if ev.supports is not supporting:
            continue
        if ev.source.is_credible and all(
            (s.name != ev.source.name) for s in seen
        ):
            seen.append(ev.source)
    return seen


def classify(evidence: List[Evidence]) -> str:
    """Derive the classification level from the evidence alone.

    Deterministic and explainable: the same evidence always maps to the same
    level.
    """
    if not evidence:
        return UNKNOWN

    contradicting = [e for e in evidence if not e.supports]
    reliable_contradictions = [
        e for e in contradicting if e.source.is_credible and e.source.reliability >= 0.6
    ]
    if reliable_contradictions:
        # Contradicted by reliable evidence -> FALSE, regardless of assertions.
        return FALSE

    primary = [e for e in evidence if e.supports and e.source.is_primary
               and e.source.reliability >= 0.7]
    if primary:
        return VERIFIED

    credible_independent = _independent_sources(evidence, supporting=True)
    if len(credible_independent) >= 2:
        return CORROBORATED

    if any(e.supports and e.source.is_credible for e in evidence):
        # Some support, but not primary and not independently corroborated.
        return PLAUSIBLE

    if any(e.supports for e in evidence):
        # Only weak/anonymous support.
        return SPECULATIVE

    # Evidence exists but none of it supports the claim.
    return UNKNOWN


def _rank(level: str) -> int:
    try:
        return LEVEL_ORDER.index(level)
    except ValueError as exc:  # pragma: no cover - guarded by callers
        raise EvidenceError(f"unknown level '{level}'") from exc


def promote(current: str, evidence: List[Evidence]) -> str:
    """Return the level the evidence actually supports, never a promotion up.

    This is the guard against "promoting speculation to verified": the result is
    the *minimum* of the current level and the level the evidence supports, so
    evidence can only hold a finding back, never lift it beyond what it proves.
    """
    supported = classify(evidence)
    return LEVEL_ORDER[min(_rank(current), _rank(supported))]


@dataclass
class Finding:
    """A claim under investigation, with its evidence and classification."""

    finding_id: str
    claim: str
    domain: str = "unknown"
    evidence: List[Evidence] = field(default_factory=list)
    level: str = UNKNOWN
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def add_evidence(self, evidence: Evidence) -> str:
        """Attach evidence and recompute the level (monotone, evidence-bound)."""
        self.evidence.append(evidence)
        self.level = classify(self.evidence)
        self.updated_at = utcnow()
        return self.level

    def recompute(self) -> str:
        self.level = classify(self.evidence)
        self.updated_at = utcnow()
        return self.level

    def try_promote(self, level: str) -> str:
        """Attempt to set a level; refuses anything the evidence cannot support."""
        new = promote(self.level, self.evidence)
        if _rank(level) > _rank(new):
            raise EvidenceError(
                f"refusing to promote '{self.finding_id}' to '{level}': "
                f"evidence supports at most '{new}'"
            )
        self.level = level
        self.updated_at = utcnow()
        return self.level

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "claim": self.claim,
            "domain": self.domain,
            "level": self.level,
            "level_label": LEVEL_LABELS.get(self.level, ""),
            "tags": list(self.tags),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "evidence": [e.to_dict() for e in self.evidence],
        }


__all__ = [
    "VERIFIED",
    "CORROBORATED",
    "PLAUSIBLE",
    "SPECULATIVE",
    "FALSE",
    "UNKNOWN",
    "LEVEL_ORDER",
    "LEVEL_LABELS",
    "PRIMARY_KINDS",
    "CREDIBLE_KINDS",
    "EvidenceError",
    "Source",
    "Evidence",
    "Finding",
    "classify",
    "promote",
]
