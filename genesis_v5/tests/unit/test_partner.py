"""Tests for the thought-partner: offers options, never decides for the user."""
from __future__ import annotations

from genesis.bootstrap import build
from genesis.care.companion import CareCompanion, CareMode
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.reflection.partner import ThoughtPartner


def _partner(memory=None) -> ThoughtPartner:
    return ThoughtPartner(
        CareCompanion(),
        ParallelGenerator(seed=1),
        memory=memory,
    )


def test_turn_offers_options_and_support() -> None:
    turn = _partner().turn("I am stuck designing a cache", shots=64)
    assert turn.care.acknowledgement
    assert len(turn.options) == 3
    assert turn.chosen is None


def test_crisis_turn_offers_no_options_and_refers() -> None:
    turn = _partner().turn("I want to die", shots=64)
    assert turn.care.mode is CareMode.PROFESSIONAL_REFERRAL
    assert turn.options == []
    assert turn.care.referral


def test_user_makes_the_choice_not_the_partner() -> None:
    partner = _partner()
    turn = partner.turn("help me decide", shots=64)
    assert turn.chosen is None  # partner does not choose
    updated = partner.choose(turn.turn_id, "latent_inversion")
    assert updated.chosen == "latent_inversion"
    assert partner.summary()["decided_for_user"] == 0


def test_history_records_turns() -> None:
    partner = _partner()
    partner.turn("one", shots=32)
    partner.turn("two", shots=32)
    assert len(partner.history()) == 2


def test_memory_persists_turns_when_provided() -> None:
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    partner = ThoughtPartner(
        CareCompanion(),
        ParallelGenerator(seed=1),
        memory=kernel.memory,
    )
    turn = partner.turn("remember this", shots=32)
    from genesis.core import MemoryScope

    entry = kernel.memory.read(MemoryScope.SESSION, f"turn:{turn.turn_id}")
    assert entry is not None
