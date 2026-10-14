"""A thought-partner: offers options, the person chooses.

This ties ``genesis.care`` and ``genesis.generation`` together. When someone
brings a problem — tired, stuck, or simply unsure — the partner listens without
judging, generates a few honest options, and hands the choice back. It never
decides for the person and never blames them.

It also remembers the session so a returning person is not starting from zero,
using the existing memory fabric under the normal write policies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from genesis.care.companion import CareCompanion, CareMode, CareResponse
from genesis.core import MemoryScope, new_id, now_ms
from genesis.generation.generator import Branch, ParallelGenerator


@dataclass
class PartnerTurn:
    """One exchange: what came in, what was offered, what the person chose."""

    turn_id: str
    input: str
    care: CareResponse
    options: list[Branch]
    chosen: str | None = None
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "input": self.input,
            "care": self.care.to_dict(),
            "options": [o.to_dict() for o in self.options],
            "chosen": self.chosen,
            "ts_ms": self.ts_ms,
        }


class ThoughtPartner:
    """Listen, offer options, let the person choose. Never decide for them."""

    def __init__(
        self,
        companion: CareCompanion,
        generator: ParallelGenerator,
        *,
        memory: Any = None,
        actor: str = "user",
    ) -> None:
        self.companion = companion
        self.generator = generator
        self.memory = memory
        self.actor = actor
        self._turns: list[PartnerTurn] = []

    def turn(self, message: str, *, goal: str = "", shots: int = 256) -> PartnerTurn:
        """Respond to a message with support and a few options."""
        care = self.companion.respond(message, goal=goal)

        # In a crisis the partner does not generate options or push forward; it
        # only points to real human help. Nothing to choose from until safe.
        if care.mode is CareMode.PROFESSIONAL_REFERRAL:
            turn = PartnerTurn(
                turn_id=new_id("turn"),
                input=message,
                care=care,
                options=[],
            )
        else:
            generation = self.generator.generate(message, shots=shots)
            turn = PartnerTurn(
                turn_id=new_id("turn"),
                input=message,
                care=care,
                options=generation.ranked(),
            )

        self._turns.append(turn)
        self._remember(turn)
        return turn

    def choose(self, turn_id: str, branch_name: str) -> PartnerTurn:
        """Record the person's own choice for a turn."""
        for turn in self._turns:
            if turn.turn_id == turn_id:
                turn.chosen = branch_name
                self._remember(turn)
                return turn
        raise KeyError(f"unknown turn {turn_id}")

    def history(self) -> list[PartnerTurn]:
        return list(self._turns)

    def summary(self) -> dict[str, Any]:
        return {
            "turns": len(self._turns),
            "options_offered": sum(len(t.options) for t in self._turns),
            "choices_made": sum(1 for t in self._turns if t.chosen),
            "decided_for_user": 0,
        }

    # ------------------------------------------------------------------
    def _remember(self, turn: PartnerTurn) -> None:
        if self.memory is None:
            return
        try:
            self.memory.write(
                MemoryScope.SESSION,
                f"turn:{turn.turn_id}",
                {
                    "input": turn.input,
                    "mode": turn.care.mode.value,
                    "options": [o.name for o in turn.options],
                    "chosen": turn.chosen,
                },
                metadata={"kind": "thought_partner"},
                actor=self.actor,
            )
        except Exception:
            # Memory is best-effort; a failure to persist must not break the
            # conversation. The failure is recorded by the memory provider.
            return
