"""Resilient failure response: acknowledge, learn, continue — without blame.

When something goes wrong a system has two options. It can react like an
untrained mind: look for someone to blame, escalate to anger, and cause more
damage. Or it can behave like a steady one: note what happened, take the
lesson, and move on without condemning itself or anyone else.

``ResiliencePolicy`` implements the second option. It classifies a failure,
decides whether to continue, and hands back a *lesson* — never a verdict about
who is at fault. Two rules are absolute:

- **No blame.** ``attribute_blame`` is always False. Failures are events, not
  sins; the report describes the cause, never assigns guilt.
- **No spiral.** ``should_continue`` is bounded by ``max_continuations``, so a
  failure cannot trigger an infinite retry loop.

This module does not hide failures — it pairs with ``genesis.transparency``,
which records every one of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.core import new_id, now_ms


class FailureKind(str, Enum):
    """Classification of what went wrong."""

    TRANSIENT = "transient"      # temporary; worth one more attempt
    PERMANENT = "permanent"      # will not succeed by retrying
    EXTERNAL = "external"        # outside our control (network, provider)
    UNKNOWN = "unknown"


@dataclass
class FailureEvent:
    """A failure as an event, not a verdict."""

    component: str
    what: str
    kind: FailureKind = FailureKind.UNKNOWN
    event_id: str = field(default_factory=lambda: new_id("res"))
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "component": self.component,
            "what": self.what,
            "kind": self.kind.value,
            "ts_ms": self.ts_ms,
        }


@dataclass
class Response:
    """How the system responds to a failure."""

    failure: FailureEvent
    should_continue: bool
    lesson: str
    retry_advised: bool
    attribute_blame: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure": self.failure.to_dict(),
            "should_continue": self.should_continue,
            "lesson": self.lesson,
            "retry_advised": self.retry_advised,
            "attribute_blame": self.attribute_blame,
        }


class ResiliencePolicy:
    """Decide how to carry on after a failure, without blame or spiralling."""

    def __init__(
        self,
        *,
        max_continuations: int = 3,
        continue_on: tuple[FailureKind, ...] = (
            FailureKind.TRANSIENT,
            FailureKind.EXTERNAL,
            FailureKind.UNKNOWN,
        ),
    ) -> None:
        self.max_continuations = max(0, max_continuations)
        self.continue_on = continue_on
        self._continuations = 0
        self._events: list[Response] = []

    def respond(self, event: FailureEvent) -> Response:
        """Produce a response to a failure.

        Continuing is allowed only for kinds worth retrying and only while the
        continuation budget lasts. The lesson is stated as a fact about the
        situation; blame is never assigned.
        """
        retryable = event.kind in self.continue_on
        under_budget = self._continuations < self.max_continuations
        should_continue = retryable and under_budget
        if should_continue:
            self._continuations += 1

        response = Response(
            failure=event,
            should_continue=should_continue,
            lesson=self._lesson(event),
            retry_advised=should_continue,
            attribute_blame=False,
        )
        self._events.append(response)
        return response

    @staticmethod
    def _lesson(event: FailureEvent) -> str:
        return {
            FailureKind.TRANSIENT: (
                f"{event.component} failed temporarily; a single retry is "
                "reasonable, then move on."
            ),
            FailureKind.EXTERNAL: (
                f"{event.component} failed for reasons outside our control; "
                "note it and continue with what is available."
            ),
            FailureKind.PERMANENT: (
                f"{event.component} cannot succeed by retrying; continue "
                "without it rather than repeating the attempt."
            ),
            FailureKind.UNKNOWN: (
                f"{event.component} failed for an unclear reason; record it "
                "and continue, watching for a pattern."
            ),
        }[event.kind]

    def reset(self) -> None:
        """Start a fresh continuation budget (a new task, not a grudge)."""
        self._continuations = 0

    def events(self) -> list[Response]:
        return list(self._events)

    def summary(self) -> dict[str, Any]:
        return {
            "failures_seen": len(self._events),
            "continuations_used": self._continuations,
            "continuations_left": self.max_continuations - self._continuations,
            "blame_assigned": 0,
        }
