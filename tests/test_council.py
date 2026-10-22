"""Tests for the multi-LLM council.

The council's job is orchestration: ask several models, then reconcile. These
tests drive it with small in-process providers that return fixed text, so the
reconciliation logic (voting, best-pick, synthesis, consensus) is exercised on
real code paths instead of being mocked out.
"""
from __future__ import annotations

import asyncio

from genesis_protocol.ai.council import (
    CouncilMember,
    CouncilStrategy,
    LLMCouncil,
    answer_similarity,
)
from genesis_protocol.ai.providers.base_provider import AIResponse


class FakeProvider:
    """A provider that returns a canned answer and never touches the network."""

    def __init__(self, name: str, answer: str, fail: bool = False):
        self.name = name
        self.answer = answer
        self.fail = fail
        self.calls = 0

    def is_configured(self) -> bool:
        return True

    def should_use(self) -> bool:
        return True

    def get_default_model(self) -> str:
        return f"{self.name}-model"

    async def generate(self, request) -> AIResponse:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return AIResponse(content=self.answer, provider=self.name,
                          model=f"{self.name}-model", tokens_used=10, latency_ms=5)


class FakeScoring:
    """Minimal scoring stand-in that ranks providers in a fixed order."""

    def __init__(self, order):
        self._order = order

    def analyze_intent(self, query):
        return None

    def score_models(self, query, intent, available):
        from genesis_protocol.ai.scoring_engine import ModelScore
        return [ModelScore(provider=p, model_name=f"{p}-model", score=1.0 - i * 0.1)
                for i, p in enumerate(self._order) if p in available]


class FakeChain:
    """A provider chain stub exposing only what the council uses."""

    def __init__(self, providers, order=None):
        self._providers = providers
        self._scoring = FakeScoring(order or list(providers))

    def get_available_providers(self):
        return list(self._providers)

    def _map_model_to_provider(self, model, provider, provider_obj):
        return model


def _council(providers, order=None):
    return LLMCouncil(chain=FakeChain(providers, order))


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_similarity_bounds():
    assert answer_similarity("same words here", "same words here") == 1.0
    assert answer_similarity("alpha beta", "gamma delta") == 0.0
    assert 0.0 < answer_similarity("the cat sat", "the cat ran") < 1.0


def test_best_strategy_returns_a_member_answer():
    providers = {
        "a": FakeProvider("a", "answer from a"),
        "b": FakeProvider("b", "answer from b"),
    }
    result = run(_council(providers).deliberate(
        [{"role": "user", "content": "hi"}], strategy=CouncilStrategy.BEST, size=2))
    assert result.success
    assert result.answer in {"answer from a", "answer from b"}
    assert result.winner is not None
    assert len(result.members) == 2


def test_a_failing_member_does_not_fail_the_council():
    providers = {
        "a": FakeProvider("a", "good answer", fail=True),
        "b": FakeProvider("b", "the surviving answer"),
    }
    result = run(_council(providers).deliberate(
        [{"role": "user", "content": "hi"}], strategy=CouncilStrategy.BEST, size=2))
    assert result.success
    assert result.answer == "the surviving answer"
    assert result.winner.provider == "b"


def test_all_members_failing_is_reported():
    providers = {
        "a": FakeProvider("a", "", fail=True),
        "b": FakeProvider("b", "", fail=True),
    }
    result = run(_council(providers).deliberate(
        [{"role": "user", "content": "hi"}], strategy=CouncilStrategy.BEST, size=2))
    assert not result.success
    assert "failed" in result.error.lower()


def test_vote_picks_the_majority_answer():
    providers = {
        "a": FakeProvider("a", "the capital of France is Paris"),
        "b": FakeProvider("b", "the capital of France is Paris"),
        "c": FakeProvider("c", "I like turtles"),
    }
    result = run(_council(providers).deliberate(
        [{"role": "user", "content": "capital of France?"}], strategy=CouncilStrategy.VOTE, size=3))
    assert result.success
    assert "Paris" in result.answer
    assert result.consensus >= 0.5


def test_consensus_is_low_when_models_disagree():
    providers = {
        "a": FakeProvider("a", "one two three four five"),
        "b": FakeProvider("b", "six seven eight nine ten"),
    }
    result = run(_council(providers).deliberate(
        [{"role": "user", "content": "hi"}], strategy=CouncilStrategy.VOTE, size=2))
    assert result.success
    assert result.consensus <= 0.5


def test_no_providers_reports_cleanly():
    result = run(_council({}).deliberate([{"role": "user", "content": "hi"}]))
    assert not result.success
    assert "providers" in result.error.lower()


def test_candidates_are_one_per_provider():
    providers = {
        "a": FakeProvider("a", "x"),
        "b": FakeProvider("b", "y"),
        "c": FakeProvider("c", "z"),
    }
    council = _council(providers, order=["a", "b", "c"])
    picked = council._pick_candidates("hi", ["a", "b", "c"], size=2)
    assert len(picked) == 2
    assert len({p for p, _ in picked}) == 2


def test_member_ok_flag():
    assert CouncilMember(provider="a", model="m", content="hi").ok
    assert not CouncilMember(provider="a", model="m", content="", error="boom").ok
