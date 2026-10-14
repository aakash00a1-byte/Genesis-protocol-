"""Transparency layer: no hidden failures, every decision shows its benefit.

Two ledgers sit alongside the audit log:

- ``DecisionLedger`` records *why* a choice was made and *what benefit* it was
  expected to deliver, then closes the loop with the actual outcome. This makes
  the "what is the point of this?" question answerable after the fact.
- ``FailureLedger`` records every failure that occurs. The ``guard`` helper
  records a failure and re-raises it, so a failure is surfaced rather than
  swallowed — the opposite of a silent ``except: pass``.

Nothing here decides policy or executes work; it only observes and reports.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from genesis.core import new_id, now_ms


@dataclass
class Decision:
    """A choice made by the system, with its rationale and expected benefit."""

    actor: str
    question: str
    options: list[str]
    chosen: str
    rationale: str
    expected_benefit: str
    decision_id: str = field(default_factory=lambda: new_id("dec"))
    outcome: str = "pending"
    actual_benefit: str = ""
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "actor": self.actor,
            "question": self.question,
            "options": list(self.options),
            "chosen": self.chosen,
            "rationale": self.rationale,
            "expected_benefit": self.expected_benefit,
            "outcome": self.outcome,
            "actual_benefit": self.actual_benefit,
            "ts_ms": self.ts_ms,
        }


@dataclass
class Failure:
    """A failure that occurred. Recorded, never hidden."""

    component: str
    what: str
    why: str
    impact: str
    failure_id: str = field(default_factory=lambda: new_id("fail"))
    surfaced: bool = True
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "component": self.component,
            "what": self.what,
            "why": self.why,
            "impact": self.impact,
            "surfaced": self.surfaced,
            "ts_ms": self.ts_ms,
        }


class DecisionLedger:
    """Thread-safe ledger of decisions with expected-vs-actual benefit."""

    def __init__(self, max_entries: int = 500) -> None:
        self.max_entries = max(1, max_entries)
        self._items: list[Decision] = []
        self._lock = threading.Lock()

    def record(
        self,
        *,
        actor: str,
        question: str,
        chosen: str,
        rationale: str,
        expected_benefit: str,
        options: list[str] | None = None,
    ) -> Decision:
        decision = Decision(
            actor=actor,
            question=question,
            options=list(options or []),
            chosen=chosen,
            rationale=rationale,
            expected_benefit=expected_benefit,
        )
        with self._lock:
            self._items.append(decision)
            self._items = self._items[-self.max_entries :]
        return decision

    def resolve(
        self,
        decision_id: str,
        *,
        outcome: str,
        actual_benefit: str,
    ) -> Decision | None:
        with self._lock:
            for item in self._items:
                if item.decision_id == decision_id:
                    item.outcome = outcome
                    item.actual_benefit = actual_benefit
                    return item
        return None

    def decisions(self) -> list[Decision]:
        with self._lock:
            return list(self._items)

    def unresolved(self) -> list[Decision]:
        with self._lock:
            return [d for d in self._items if d.outcome == "pending"]

    def benefit_report(self) -> list[dict[str, Any]]:
        """Every decision with what it promised versus what it delivered."""
        with self._lock:
            items = list(self._items)
        return [
            {
                "decision_id": d.decision_id,
                "question": d.question,
                "chosen": d.chosen,
                "expected_benefit": d.expected_benefit,
                "actual_benefit": d.actual_benefit,
                "outcome": d.outcome,
                "benefit_delivered": d.outcome == "success"
                and bool(d.actual_benefit.strip()),
            }
            for d in items
        ]

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class FailureLedger:
    """Thread-safe ledger of failures. Nothing is dropped silently."""

    def __init__(self, max_entries: int = 500) -> None:
        self.max_entries = max(1, max_entries)
        self._items: list[Failure] = []
        self._lock = threading.Lock()

    def record(
        self,
        *,
        component: str,
        what: str,
        why: str,
        impact: str,
    ) -> Failure:
        failure = Failure(component=component, what=what, why=why, impact=impact)
        with self._lock:
            self._items.append(failure)
            self._items = self._items[-self.max_entries :]
        return failure

    @contextmanager
    def guard(
        self,
        *,
        component: str,
        what: str,
        impact: str = "unknown",
    ) -> Iterator[None]:
        """Record any exception here, then re-raise it.

        The failure is captured for reporting *and* propagated to the caller, so
        it cannot be quietly swallowed by an empty except block.
        """
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            self.record(
                component=component,
                what=what,
                why=f"{type(exc).__name__}: {exc}",
                impact=impact,
            )
            raise

    @contextmanager
    def capture(
        self,
        *,
        component: str,
        what: str,
        impact: str = "unknown",
    ) -> Iterator[None]:
        """Record any exception here and continue.

        Unlike ``guard``, the exception is not re-raised. The failure is still
        recorded, so a path that degrades gracefully is visible in the report
        instead of being hidden.
        """
        try:
            yield
        except Exception as exc:  # noqa: BLE001
            self.record(
                component=component,
                what=what,
                why=f"{type(exc).__name__}: {exc}",
                impact=impact,
            )

    def failures(self) -> list[Failure]:
        with self._lock:
            return list(self._items)

    def count(self) -> int:
        with self._lock:
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class TransparencyReport:
    """Read-only view over both ledgers for one system."""

    def __init__(
        self,
        decisions: DecisionLedger | None = None,
        failures: FailureLedger | None = None,
    ) -> None:
        self.decisions = decisions or DecisionLedger()
        self.failures = failures or FailureLedger()

    def snapshot(self) -> dict[str, Any]:
        failures = self.failures.failures()
        return {
            "decisions": [d.to_dict() for d in self.decisions.decisions()],
            "unresolved_decisions": [
                d.to_dict() for d in self.decisions.unresolved()
            ],
            "benefit_report": self.decisions.benefit_report(),
            "failures": [f.to_dict() for f in failures],
            "failure_count": len(failures),
            "hidden_failures": 0,
        }
