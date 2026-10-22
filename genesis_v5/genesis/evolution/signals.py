"""Signals: what the system notices about its own recent behaviour.

A signal is a plain observation, never an action. Three kinds are collected:

- ``WeaknessSignal``   — something that went wrong (a failure, a denial, an
  agent error). Weaknesses are facts, not verdicts.
- ``HealthSignal``     — a metric outside its expected band (e.g. a rising
  denial rate). A health signal says "look here", not "this is broken".
- ``ImprovementSignal``— an opportunity that is not a defect (repeated work
  that could be consolidated, a test that is missing).

``SignalCollector`` reads the transparency ledgers and metrics and produces
these signals. It is deliberately read-only and dependency-free: it holds no
lock on the system it observes.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from genesis.core import now_ms

# A weakness at or above this severity blocks the "all clear" verdict.
BLOCKING_SEVERITIES = {"high", "critical"}


@dataclass
class WeaknessSignal:
    """A recorded failure or denial, surfaced as an improvement candidate."""

    component: str
    what: str
    why: str = ""
    impact: str = ""
    severity: str = "medium"  # low | medium | high | critical
    source: str = "failure_ledger"
    signal_id: str = field(default_factory=lambda: _signal_id("weak"))
    ts_ms: int = field(default_factory=now_ms)

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "weakness",
            "signal_id": self.signal_id,
            "component": self.component,
            "what": self.what,
            "why": self.why,
            "impact": self.impact,
            "severity": self.severity,
            "source": self.source,
            "ts_ms": self.ts_ms,
        }


@dataclass
class HealthSignal:
    """A metric outside its expected band."""

    metric: str
    value: float
    expectation: str
    severity: str = "low"
    signal_id: str = field(default_factory=lambda: _signal_id("health"))
    ts_ms: int = field(default_factory=now_ms)

    @property
    def blocking(self) -> bool:
        return self.severity in BLOCKING_SEVERITIES

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "health",
            "signal_id": self.signal_id,
            "metric": self.metric,
            "value": self.value,
            "expectation": self.expectation,
            "severity": self.severity,
            "ts_ms": self.ts_ms,
        }


@dataclass
class ImprovementSignal:
    """An opportunity that is not a defect."""

    area: str
    opportunity: str
    rationale: str = ""
    confidence: float = 0.5
    signal_id: str = field(default_factory=lambda: _signal_id("imp"))
    ts_ms: int = field(default_factory=now_ms)

    @property
    def blocking(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "improvement",
            "signal_id": self.signal_id,
            "area": self.area,
            "opportunity": self.opportunity,
            "rationale": self.rationale,
            "confidence": round(self.confidence, 4),
            "ts_ms": self.ts_ms,
        }


def _signal_id(prefix: str) -> str:
    from genesis.core import new_id

    return new_id(prefix)


# ----------------------------------------------------------------------
# Collection
# ----------------------------------------------------------------------
class SignalCollector:
    """Turn recent system behaviour into signals. Read-only."""

    def __init__(
        self,
        *,
        failure_ledger: Any = None,
        decision_ledger: Any = None,
        metrics: Any = None,
        denial_rate_threshold: float = 0.2,
        unresolved_threshold: int = 5,
    ) -> None:
        self.failure_ledger = failure_ledger
        self.decision_ledger = decision_ledger
        self.metrics = metrics
        self.denial_rate_threshold = denial_rate_threshold
        self.unresolved_threshold = unresolved_threshold

    def collect(self) -> list[Any]:
        """Return every signal the current state yields, in a stable order."""
        signals: list[Any] = []
        signals.extend(self.weaknesses())
        signals.extend(self.health())
        signals.extend(self.opportunities())
        return signals

    # -- weaknesses -----------------------------------------------------
    def weaknesses(self) -> list[WeaknessSignal]:
        out: list[WeaknessSignal] = []
        for failure in _items(self.failure_ledger, "failures"):
            out.append(
                WeaknessSignal(
                    component=str(getattr(failure, "component", "unknown")),
                    what=str(getattr(failure, "what", "")),
                    why=str(getattr(failure, "why", "")),
                    impact=str(getattr(failure, "impact", "")),
                    severity=self._failure_severity(failure),
                    source="failure_ledger",
                )
            )
        return out

    def health(self) -> list[HealthSignal]:
        out: list[HealthSignal] = []
        metrics = self.metrics
        if metrics is None:
            return out
        requested = _counter(metrics, "kernel.agent_tool_requests")
        denied = _counter(metrics, "kernel.agent_tool_denied")
        if requested > 0:
            rate = denied / requested
            if rate >= self.denial_rate_threshold:
                out.append(
                    HealthSignal(
                        metric="agent_tool_denial_rate",
                        value=round(rate, 4),
                        expectation=f"< {self.denial_rate_threshold}",
                        severity="medium" if rate < 0.5 else "high",
                    )
                )
        unresolved = _items(self.decision_ledger, "unresolved")
        if len(unresolved) >= self.unresolved_threshold:
            out.append(
                HealthSignal(
                    metric="unresolved_decisions",
                    value=float(len(unresolved)),
                    expectation=f"< {self.unresolved_threshold}",
                    severity="low",
                )
            )
        return out

    def opportunities(self) -> list[ImprovementSignal]:
        """Opportunities inferred from repeated weaknesses.

        Two failures in the same component is not twice the problem — it is a
        pattern, and a pattern is what an improvement should target.
        """
        by_component: dict[str, int] = {}
        for weakness in self.weaknesses():
            by_component[weakness.component] = by_component.get(weakness.component, 0) + 1
        out: list[ImprovementSignal] = []
        for component, count in sorted(by_component.items()):
            if count >= 2:
                out.append(
                    ImprovementSignal(
                        area=component,
                        opportunity=(
                            f"consolidate repeated handling in {component} "
                            f"({count} recent failures)"
                        ),
                        rationale="the same component failed more than once",
                        confidence=min(0.9, 0.4 + 0.1 * count),
                    )
                )
        return out

    @staticmethod
    def _failure_severity(failure: Any) -> str:
        """Severity from impact text. Honest, conservative, deterministic."""
        text = f"{getattr(failure, 'impact', '')} {getattr(failure, 'what', '')}".lower()
        if any(k in text for k in ("security", "credential", "breach", "audit")):
            return "high"
        if any(k in text for k in ("data loss", "corrupt", "silent", "hidden")):
            return "high"
        return "medium"


def _items(ledger: Any, accessor: str) -> list[Any]:
    if ledger is None:
        return []
    fn = getattr(ledger, accessor, None)
    if fn is None:
        return []
    value = fn() if callable(fn) else fn
    return list(value or [])


def _counter(metrics: Any, name: str) -> int:
    fn = getattr(metrics, "counter", None)
    if fn is None:
        return 0
    try:
        return int(fn(name))
    except (TypeError, ValueError):
        return 0


def summarize(signals: Iterable[Any]) -> dict[str, int]:
    """Count signals by kind — handy for reports and tests."""
    counts = {"weakness": 0, "health": 0, "improvement": 0}
    for signal in signals:
        kind = getattr(signal, "to_dict", lambda: {})().get("kind")
        if kind in counts:
            counts[kind] += 1
    return counts
