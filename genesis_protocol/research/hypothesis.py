"""Hypotheses, including the ones that turned out to be wrong.

A hypothesis is only scientific if something could refute it, so the model here
requires a ``falsifiable_test`` before it can be tested at all. Two rules are
enforced rather than documented:

* **Supported needs an independent check.** ``support()`` refuses a reference
  that did not come from a checker, because "it looked right" is not support.
* **Refuted is permanent.** A refuted hypothesis cannot be deleted, only
  superseded by a new one. The negative result is the most valuable record in
  the book.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

PROPOSED = "proposed"
TESTING = "testing"
SUPPORTED = "supported"
REFUTED = "refuted"
INCONCLUSIVE = "inconclusive"

_TERMINAL = frozenset({REFUTED})


class HypothesisError(ValueError):
    """A hypothesis transition that science does not allow."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Hypothesis:
    """One falsifiable claim and the evidence for or against it."""

    id: str
    statement: str
    falsifiable_test: str
    prediction: str = ""
    status: str = PROPOSED
    evidence: list[dict] = field(default_factory=list)
    superseded_by: str | None = None
    created_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "statement": self.statement,
            "falsifiable_test": self.falsifiable_test,
            "prediction": self.prediction,
            "status": self.status,
            "evidence": list(self.evidence),
            "superseded_by": self.superseded_by,
            "created_at": self.created_at,
        }


class HypothesisBook:
    """A book that only ever grows."""

    def __init__(self):
        self._items: dict[str, Hypothesis] = {}
        self._order: list[str] = []

    # -- writes -------------------------------------------------------------
    def add(self, hypothesis_id: str, statement: str, falsifiable_test: str,
            prediction: str = "") -> Hypothesis:
        if not (statement or "").strip():
            raise HypothesisError("a hypothesis needs a statement")
        if not (falsifiable_test or "").strip():
            raise HypothesisError(
                "a hypothesis needs a falsifiable test; without one it cannot be science"
            )
        if hypothesis_id in self._items:
            raise HypothesisError(f"hypothesis '{hypothesis_id}' already exists")
        item = Hypothesis(hypothesis_id, statement.strip(), falsifiable_test.strip(),
                          prediction.strip())
        self._items[hypothesis_id] = item
        self._order.append(hypothesis_id)
        return item

    def start_testing(self, hypothesis_id: str) -> Hypothesis:
        item = self._get(hypothesis_id)
        if item.status in _TERMINAL:
            raise HypothesisError(f"'{hypothesis_id}' is {item.status}; it cannot be re-opened")
        item.status = TESTING
        return item

    def support(self, hypothesis_id: str, verification: dict) -> Hypothesis:
        """Mark supported - only with an independent verification result."""
        item = self._get(hypothesis_id)
        if item.status in _TERMINAL:
            raise HypothesisError(f"'{hypothesis_id}' is {item.status}")
        if not verification or verification.get("independent") is not True:
            raise HypothesisError(
                "support requires an independent verification (independent=True)"
            )
        if verification.get("passed") is not True:
            raise HypothesisError("support requires a verification that passed")
        item.status = SUPPORTED
        item.evidence.append({"kind": "support", "at": _now(), "verification": dict(verification)})
        return item

    def refute(self, hypothesis_id: str, reason: str, verification: dict | None = None) -> Hypothesis:
        """Mark refuted. Terminal, recorded, never removed."""
        item = self._get(hypothesis_id)
        if item.status == REFUTED:
            return item
        if not (reason or "").strip():
            raise HypothesisError("a refutation needs a reason")
        item.status = REFUTED
        item.evidence.append({
            "kind": "refutation", "at": _now(), "reason": reason.strip(),
            "verification": dict(verification or {}),
        })
        return item

    def mark_inconclusive(self, hypothesis_id: str, reason: str = "") -> Hypothesis:
        item = self._get(hypothesis_id)
        if item.status in _TERMINAL:
            raise HypothesisError(f"'{hypothesis_id}' is {item.status}")
        item.status = INCONCLUSIVE
        item.evidence.append({"kind": "inconclusive", "at": _now(), "reason": reason})
        return item

    def supersede(self, hypothesis_id: str, new_id: str) -> None:
        old = self._get(hypothesis_id)
        self._get(new_id)
        old.superseded_by = new_id

    def remove(self, *args, **kwargs):
        raise PermissionError("the hypothesis book is append-only; refuted hypotheses stay")

    # -- reads --------------------------------------------------------------
    def _get(self, hypothesis_id: str) -> Hypothesis:
        if hypothesis_id not in self._items:
            raise HypothesisError(f"unknown hypothesis '{hypothesis_id}'")
        return self._items[hypothesis_id]

    def get(self, hypothesis_id: str) -> Hypothesis:
        return self._get(hypothesis_id)

    def all(self) -> list[Hypothesis]:
        return [self._items[i] for i in self._order]

    def refuted(self) -> list[Hypothesis]:
        return [h for h in self.all() if h.status == REFUTED]

    def supported(self) -> list[Hypothesis]:
        return [h for h in self.all() if h.status == SUPPORTED]
