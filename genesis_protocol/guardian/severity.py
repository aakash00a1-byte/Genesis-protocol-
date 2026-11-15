"""Threat severity classification with evidence-based confidence (V7 P6).

The P5 detectors emit a raw severity. P6 turns a raw finding into a *classified*
one: a normalised severity, an explicit confidence in ``[0, 1]`` and the list of
reasons that produced that confidence. Nothing here guesses - each reason is a
fact drawn from the finding (threshold crossing, identity verification, source
tier, corroborating detectors).

Confidence is deliberately separate from severity. A high-severity observation
made on weak evidence (a single unverified signal) must not be treated as a
confirmed incident, and the confidence reasons make that distinction auditable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SEVERITIES = ("info", "low", "medium", "high", "critical")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}

# Detector -> the severity it carries when its evidence is a bare threshold hit.
BASE_SEVERITY: Dict[str, str] = {
    "auth_bruteforce": "medium",
    "webhook_abuse": "medium",
    "api_burst": "low",
    "identity_spoofing": "high",
    "privilege_escalation": "high",
    "repeated_denials": "medium",
    "secret_exposure": "critical",
    "unregistered_tool": "high",
    "execution_after_denial": "critical",
    "grant_escape": "high",
    "policy_violation": "medium",
    "unusual_tool_variety": "low",
    "repeated_denied_actions": "medium",
    "memory_db_corrupt": "critical",
    "memory_db_unreadable": "high",
    "memory_db_missing": "low",
    "task_store_corrupt": "high",
    "high_cpu": "medium",
    "high_memory": "medium",
    "high_disk": "medium",
    "behaviour_change": "medium",
    "resource_unavailable": "high",
}

# Detectors whose confidence depends on how far past the threshold the evidence is.
_THRESHOLD_DETECTORS = {
    "auth_bruteforce", "webhook_abuse", "api_burst", "repeated_denials", "repeated_denied_actions",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class ClassifiedFinding:
    """A finding with a normalised severity and an explained confidence."""

    detector: str
    severity: str
    confidence: float
    confidence_reasons: List[str] = field(default_factory=list)
    raw_severity: str = "info"
    actor: Optional[str] = None
    subject: Optional[str] = None
    session: Optional[str] = None
    title: str = ""
    description: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    classified_at: str = field(default_factory=_utcnow)

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["rank"] = self.rank
        return data


class SeverityClassifier:
    """Classifies raw findings into severity + explained confidence."""

    # Minimum confidence for a finding to be treated as "confirmed".
    CONFIRMED_CONFIDENCE = 0.7

    def classify(self, finding: Any, corroboration: int = 0) -> ClassifiedFinding:
        data = finding.to_dict() if hasattr(finding, "to_dict") else dict(finding)
        detector = str(data.get("detector") or "unknown")
        raw_severity = str(data.get("raw_severity") or data.get("severity") or "info").lower()
        if raw_severity not in SEVERITY_RANK:
            raw_severity = "info"

        reasons: List[str] = []
        confidence = 0.5
        reasons.append("base confidence 0.50")

        # Detector recognition.
        base = BASE_SEVERITY.get(detector)
        if base is None:
            reasons.append(f"detector '{detector}' is not in the catalogue (-0.15)")
            confidence -= 0.15
            base = raw_severity
        else:
            reasons.append(f"detector '{detector}' maps to baseline severity '{base}'")

        severity = max((base, raw_severity), key=lambda s: SEVERITY_RANK.get(s, 0))

        # Evidence strength: how far past the threshold the observation is.
        measured = data.get("evidence") or data.get("measured") or {}
        count = measured.get("count") if isinstance(measured, dict) else None
        threshold = measured.get("threshold") if isinstance(measured, dict) else None
        if detector in _THRESHOLD_DETECTORS and isinstance(count, (int, float)) and threshold:
            ratio = float(count) / float(threshold)
            if ratio >= 2.0:
                confidence += 0.25
                reasons.append(f"evidence is {ratio:.1f}x the threshold (+0.25)")
            elif ratio >= 1.0:
                confidence += 0.10
                reasons.append(f"evidence is {ratio:.1f}x the threshold (+0.10)")

        # Identity verification materially changes confidence for identity findings.
        if detector in ("identity_spoofing", "grant_escape", "unregistered_tool", "execution_after_denial"):
            if data.get("verified") is False:
                confidence += 0.20
                reasons.append("identity did not verify (+0.20)")
            elif data.get("verified") is True:
                confidence -= 0.20
                reasons.append("identity verified (+0.20 uncertainty)")

        # Corroboration by independent detectors raises confidence.
        if corroboration >= 2:
            confidence += 0.15
            reasons.append(f"corroborated by {corroboration} detectors (+0.15)")
        elif corroboration == 1:
            confidence += 0.08
            reasons.append("corroborated by 1 other detector (+0.08)")

        # A critical finding the detector itself produced at critical is strong.
        if severity == "critical" and base == "critical":
            confidence += 0.10
            reasons.append("detector itself reports critical (+0.10)")

        # Secret exposure confidence depends on whether a recognised pattern matched.
        if detector == "secret_exposure":
            kinds = (measured or {}).get("kinds") if isinstance(measured, dict) else None
            if kinds:
                confidence += 0.15
                reasons.append(f"recognised secret pattern(s): {kinds} (+0.15)")

        confidence = clamp(confidence)
        return ClassifiedFinding(
            detector=detector,
            severity=severity,
            confidence=round(confidence, 3),
            confidence_reasons=reasons,
            raw_severity=raw_severity,
            actor=data.get("actor"),
            subject=data.get("subject"),
            session=data.get("session"),
            title=data.get("title") or "",
            description=data.get("description") or "",
            evidence=measured if isinstance(measured, dict) else {},
        )

    def classify_many(self, findings: List[Any]) -> List[ClassifiedFinding]:
        """Classify findings, giving each the count of corroborating detectors."""
        by_actor: Dict[str, set] = {}
        for f in findings:
            data = f.to_dict() if hasattr(f, "to_dict") else dict(f)
            actor = str(data.get("actor") or data.get("subject") or data.get("agent_id") or "")
            if actor:
                by_actor.setdefault(actor, set()).add(str(data.get("detector") or ""))
        out = []
        for f in findings:
            data = f.to_dict() if hasattr(f, "to_dict") else dict(f)
            actor = str(data.get("actor") or data.get("subject") or data.get("agent_id") or "")
            others = len(by_actor.get(actor, set())) - 1
            out.append(self.classify(f, corroboration=max(0, others)))
        return out

    @classmethod
    def is_confirmed(cls, classified: ClassifiedFinding) -> bool:
        """A finding is 'confirmed' only above the confidence bar and above info."""
        return classified.confidence >= cls.CONFIRMED_CONFIDENCE and classified.rank >= SEVERITY_RANK["low"]

    @staticmethod
    def highest(findings: List[ClassifiedFinding]) -> Optional[ClassifiedFinding]:
        if not findings:
            return None
        return max(findings, key=lambda f: (f.rank, f.confidence))
