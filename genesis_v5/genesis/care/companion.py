"""A steady presence for someone who is overwhelmed.

When a person is exhausted and has nowhere left to turn, the last thing that
helps is judgement. This module is the "steady one" — it listens without
condemning, holds the person's own stated goal steady when they cannot, and
offers small next steps instead of a lecture.

Two boundaries are built into the design, not bolted on:

- **It is not a therapist.** ``CareMode.PROFESSIONAL_REFERRAL`` is reached when
  the words signal crisis. In that mode the response is empathy plus a route to
  real human help. It does not attempt to counsel, diagnose, or talk someone
  out of how they feel.
- **It never assigns blame.** As with ``genesis.resilience``, no response ever
  tells the person they are wrong, weak, or at fault.

It holds the *person's own* goal, never one it chose for them. The module
supports; it does not decide.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.core import new_id, now_ms


class CareMode(str, Enum):
    """What kind of support fits the situation."""

    STEADY = "steady"                  # ordinary overwhelm; a calm next step
    REFRAME = "reframe"                # stuck in self-blame; ease it
    PROFESSIONAL_REFERRAL = "referral"  # crisis signals; route to real help


@dataclass
class CareResponse:
    """A supportive reply. It never blames and never plays therapist."""

    mode: CareMode
    acknowledgement: str
    next_step: str
    referral: str = ""
    resource_note: str = ""
    response_id: str = field(default_factory=lambda: new_id("care"))
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "mode": self.mode.value,
            "acknowledgement": self.acknowledgement,
            "next_step": self.next_step,
            "referral": self.referral,
            "resource_note": self.resource_note,
            "blames_user": False,
            "is_therapist": False,
            "ts_ms": self.ts_ms,
        }


class CareCompanion:
    """Hold a person steady when they are at the end of their rope."""

    # Signals that the person may be in crisis. Presence of any of these
    # routes the response to a real human resource rather than a chat reply.
    CRISIS_SIGNALS: tuple[str, ...] = (
        "suicide", "suicidal", "kill myself", "end my life", "end it all",
        "self harm", "self-harm", "hurt myself", "no reason to live",
        "want to die", "better off dead", "can't go on", "cannot go on",
        "आत्महत्या", "खुद को मार", "जीना नहीं", "मर जाना",
    )

    # Signals that the person is stuck blaming themselves.
    SELF_BLAME_SIGNALS: tuple[str, ...] = (
        "my fault", "i am useless", "i'm useless", "i am a failure",
        "i'm a failure", "worthless", "i ruined", "everything is my fault",
        "i deserve", "मेरी गलती", "मैं बेकार", "मेरी वजह से",
    )

    def __init__(self) -> None:
        self._responses: list[CareResponse] = []

    def respond(self, message: str, *, goal: str = "") -> CareResponse:
        """Reply to someone who is overwhelmed.

        ``goal`` is the person's *own* goal. It is echoed back to keep them
        anchored; the companion never substitutes a goal of its own.
        """
        text = message.lower()
        mode = self._classify(text)

        if mode is CareMode.PROFESSIONAL_REFERRAL:
            response = CareResponse(
                mode=mode,
                acknowledgement=(
                    "What you are carrying sounds heavier than anyone should "
                    "have to hold alone. You do not have to hold it alone."
                ),
                next_step=(
                    "Please reach out to a real person right now — someone you "
                    "trust, or a crisis line. You deserve support from a human "
                    "being, not a machine."
                ),
                referral=self._referral_note(),
                resource_note=(
                    "This is a companion, not a therapist. It cannot provide "
                    "counselling or crisis care."
                ),
            )
        elif mode is CareMode.REFRAME:
            response = CareResponse(
                mode=mode,
                acknowledgement=(
                    "Something went wrong, and you are turning it into a "
                    "verdict on yourself. A bad moment is not proof about who "
                    "you are."
                ),
                next_step=self._small_step(goal),
                resource_note="No one here is keeping score against you.",
            )
        else:
            response = CareResponse(
                mode=mode,
                acknowledgement=(
                    "You are tired, and you have been carrying this a long "
                    "time. Being at the end of your rope is not a flaw."
                ),
                next_step=self._small_step(goal),
                resource_note="You can set this down for now and come back to it.",
            )

        self._responses.append(response)
        return response

    @staticmethod
    def _classify(text: str) -> CareMode:
        if any(signal in text for signal in CareCompanion.CRISIS_SIGNALS):
            return CareMode.PROFESSIONAL_REFERRAL
        if any(signal in text for signal in CareCompanion.SELF_BLAME_SIGNALS):
            return CareMode.REFRAME
        return CareMode.STEADY

    @staticmethod
    def _small_step(goal: str) -> str:
        if goal.strip():
            return (
                f"One small step toward what you already said you want — "
                f"'{goal.strip()}' — is enough for now. Nothing more."
            )
        return (
            "One small step is enough for now: breathe, drink some water, and "
            "name the single next thing. Nothing more."
        )

    @staticmethod
    def _referral_note() -> str:
        return (
            "In India: AASRA 91-9820466726, iCall 9152987821, or dial 112 for "
            "emergency services. Elsewhere: search for your local crisis line, "
            "or tell someone you trust today."
        )

    def responses(self) -> list[CareResponse]:
        return list(self._responses)

    def summary(self) -> dict[str, Any]:
        return {
            "responses": len(self._responses),
            "referrals_made": sum(
                1 for r in self._responses
                if r.mode is CareMode.PROFESSIONAL_REFERRAL
            ),
            "blamed_users": 0,
            "acted_as_therapist": 0,
        }
