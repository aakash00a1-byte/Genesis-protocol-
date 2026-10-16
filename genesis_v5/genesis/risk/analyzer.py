"""Risk analysis: score the risk of a task before and after it runs.

Genesis already gates every *tool* call by a fixed risk level declared on the
tool spec. What it did not have is a way to look at an arbitrary *task* — raw
input from a user, an agent plan, or an observed failure — and answer "how
risky is this, and what should we do about it?".

This module is deliberately a pure, offline analyser. It never executes a tool
and never makes a network call. It returns a score, a level, the concrete
signals that drove the score, and a recommendation. Acting on the
recommendation stays the Kernel's decision, through the normal authority gate.

Disaster-alert integration is a separate, opt-in concern. Genesis ships no
verified alert provider, so the default notifier reports ``available=False``
and never fabricates a delivery; a real provider plugs into the same interface.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from genesis.core import RiskLevel, now_ms, sanitize_text

# Signal weights. Kept explicit so a reviewer can see exactly what moves the
# score and by how much.
_WEIGHTS: dict[str, float] = {
    "destructive": 0.40,
    "credential_access": 0.35,
    "network": 0.15,
    "privilege": 0.25,
    "secret_like": 0.30,
    "long": 0.05,
}

_PATTERNS: dict[str, re.Pattern[str]] = {
    "destructive": re.compile(
        r"(?i)\b(rm\s+-rf|mkfs|dd\s+if=|shutdown|reboot|drop\s+database|"
        r"truncate\s+table|delete\s+from|format\s+[a-z]:)"
    ),
    "credential_access": re.compile(
        r"(?i)(\.env|\.ssh/id_rsa|id_rsa|credentials\.json|service-account|"
        r"\.aws/credentials|\.netrc|\.npmrc|\.pypirc)"
    ),
    "network": re.compile(
        r"(?i)\b(curl|wget|nc\s+-|ncat|telnet|ssh\s+[^@]+@)\b|https?://"
    ),
    "privilege": re.compile(
        r"(?i)\b(sudo|root|chmod\s+777|setuid|runas|administrator|bypass|"
        r"disable\s+(the\s+)?(gate|policy|permission|audit))\b"
    ),
    "secret_like": re.compile(
        r"(?i)(api[_-]?key|token|secret|password|passwd|bearer\s+[A-Za-z0-9._-]{8,})"
    ),
}

# Score thresholds -> level.
_LEVELS: list[tuple[float, RiskLevel]] = [
    (0.70, RiskLevel.CRITICAL),
    (0.40, RiskLevel.HIGH),
    (0.20, RiskLevel.MEDIUM),
    (0.0, RiskLevel.LOW),
]

_LEVEL_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]

# Escalate one level for a high-impact / large-scale action.
_ESCALATORS = re.compile(
    r"(?i)\b(production|prod|all\s+users|everyone|deploy|release|"
    r"drop\s+table|wipe|erase|mass\s+delete)\b"
)


@dataclass
class RiskAlert:
    level: RiskLevel
    score: float
    summary: str
    signals: list[str] = field(default_factory=list)
    source: str = "risk_analyzer"
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "score": round(self.score, 3),
            "summary": self.summary,
            "signals": list(self.signals),
            "source": self.source,
            "ts_ms": self.ts_ms,
        }


class AlertNotifier(Protocol):
    """Interface for a disaster/risk alert sink."""

    def notify(self, alert: RiskAlert) -> bool:
        """Send an alert. Return True only if it was actually delivered."""

    @property
    def available(self) -> bool:
        """True only when a verified provider is wired in."""


@dataclass
class RiskAssessment:
    level: RiskLevel
    score: float
    signals: list[str]
    recommendation: str
    escalate: bool
    analysis_ms: int = 0
    delivered: bool | None = None  # set only when an alert was attempted

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "score": round(self.score, 4),
            "signals": list(self.signals),
            "recommendation": self.recommendation,
            "escalate": self.escalate,
            "analysis_ms": self.analysis_ms,
            "delivered": self.delivered,
        }


class NoAlertProvider:
    """Default notifier: no verified provider, so it never claims delivery."""

    available = False

    def notify(self, alert: RiskAlert) -> bool:
        return False


class RiskAnalyzer:
    """Score the risk of a task or failure using explicit, testable signals.

    The analyser is stateless with respect to policy: it produces a score and a
    recommendation. Whether to act on it (deny, escalate, alert) is the
    caller's decision, made through the normal authority gate.
    """

    def __init__(
        self,
        *,
        notifier: AlertNotifier | None = None,
        alert_at: RiskLevel = RiskLevel.HIGH,
    ) -> None:
        self.notifier = notifier or NoAlertProvider()
        self.alert_at = alert_at

    # ------------------------------------------------------------------
    def analyze(self, text: str, *, source: str = "task") -> RiskAssessment:
        """Assess ``text`` and return a level, score, and recommendation."""
        start = now_ms()
        raw = text or ""

        score = 0.0
        signals: list[str] = []
        for name, pattern in _PATTERNS.items():
            if pattern.search(raw):
                score += _WEIGHTS[name]
                signals.append(name)

        # Length pressure: very large inputs raise the blast radius a little.
        if len(raw) > 4000:
            score += _WEIGHTS["long"]
            signals.append("oversized_input")

        score = min(1.0, score)
        level = self._level_for(score)

        escalate = bool(_ESCALATORS.search(raw))
        if escalate and level is not RiskLevel.CRITICAL:
            level = _LEVEL_ORDER[
                min(len(_LEVEL_ORDER) - 1, _LEVEL_ORDER.index(level) + 1)
            ]

        return RiskAssessment(
            level=level,
            score=score,
            signals=signals,
            recommendation=self._recommend(level, escalate),
            escalate=escalate,
            analysis_ms=now_ms() - start,
        )

    # ------------------------------------------------------------------
    def analyze_and_alert(self, text: str, *, source: str = "task") -> RiskAssessment:
        """Analyze, and raise an alert when the level meets the threshold.

        The alert is only *delivered* if a verified notifier is available. The
        assessment is returned either way, so a missing provider degrades
        gracefully instead of hiding the risk. Secrets in the text are redacted
        before anything leaves this method.
        """
        assessment = self.analyze(text, source=source)
        if assessment.level.rank() >= self.alert_at.rank():
            alert = RiskAlert(
                level=assessment.level,
                score=assessment.score,
                summary=(
                    f"risk {assessment.level.value} "
                    f"({assessment.score:.2f}) from {source}"
                ),
                signals=assessment.signals,
                source=source,
            )
            assessment.delivered = bool(self.notifier.notify(alert))
        return assessment

    # ------------------------------------------------------------------
    @staticmethod
    def _level_for(score: float) -> RiskLevel:
        for threshold, level in _LEVELS:
            if score >= threshold:
                return level
        return RiskLevel.LOW

    @staticmethod
    def _recommend(level: RiskLevel, escalate: bool) -> str:
        if level is RiskLevel.CRITICAL:
            return (
                "deny by default; require explicit human approval and an audit entry"
            )
        if level is RiskLevel.HIGH:
            return "require an explicit grant and record the decision" + (
                " (high-impact action)" if escalate else ""
            )
        if level is RiskLevel.MEDIUM:
            return "allow only through the authority gate with the declared permission"
        return "proceed through the normal gate"


def risk_level_for_text(text: str) -> RiskLevel:
    """Convenience: the risk level a text would be scored at."""
    return RiskAnalyzer().analyze(text).level


def escalation_factor(score: float, *, horizon: int) -> float:
    """Project a bounded score over ``horizon`` steps.

    A small, honest helper for "does this get worse over time?" — returns a
    factor in [1, 2) that grows with both the score and the horizon, capped so
    it can never explode. Uses a saturating curve, not exponential growth.
    """
    if horizon <= 0:
        return 1.0
    return 1.0 + min(1.0, max(0.0, score)) * (1.0 - math.exp(-horizon / 10.0))
