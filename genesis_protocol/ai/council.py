"""Genesis Protocol - Multi-LLM Council

Where the provider chain asks one model and falls back on failure, the council
asks several models *at the same time* and then reconciles their answers. That
turns "which model do we trust?" into a decision the system can make per
request instead of a hardcoded choice.

Three reconciliation strategies:

* ``BEST``      - score every answer with the QualityJudge, return the highest.
* ``VOTE``      - cluster answers by similarity, return the largest cluster's
                  answer, and report how much the models agreed.
* ``SYNTHESIS`` - hand every answer to the strongest model and ask it to merge
                  them into one, keeping points the others missed.

Members are chosen by the existing ScoringEngine so the council reuses the same
model-selection logic as normal routing rather than inventing a second one.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from enum import Enum

from genesis_protocol.ai.providers.base_provider import AIRequest
from genesis_protocol.ai.quality_judge import QualityJudge
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.council")

_WORD_RE = re.compile(r"[a-z0-9]+")


class CouncilStrategy(Enum):
    """How the council reconciles its members' answers."""
    BEST = "best"
    VOTE = "vote"
    SYNTHESIS = "synthesis"


@dataclass
class CouncilMember:
    """One model's contribution to the deliberation."""
    provider: str
    model: str
    content: str = ""
    score: float = 0.0
    latency_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.content)


@dataclass
class CouncilResult:
    """The council's decision plus the evidence behind it."""
    success: bool
    strategy: CouncilStrategy
    answer: str = ""
    winner: CouncilMember | None = None
    members: list[CouncilMember] = field(default_factory=list)
    consensus: float = 0.0
    total_latency_ms: int = 0
    error: str | None = None

    @property
    def answered_by(self) -> str:
        return f"{self.winner.provider}/{self.winner.model}" if self.winner else ""


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def answer_similarity(a: str, b: str) -> float:
    """Token-set Jaccard similarity, 0.0 to 1.0.

    Cheap, deterministic and good enough to tell "the models agree" from "the
    models disagree" without another model call.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


class LLMCouncil:
    """Ask several models, then reconcile their answers."""

    def __init__(self, chain=None, judge: QualityJudge = None):
        from genesis_protocol.ai.provider_chain import get_provider_chain

        self._chain = chain or get_provider_chain()
        self._judge = judge or QualityJudge()

    def _pick_candidates(self, query: str, available: list[str], size: int) -> list[tuple[str, str]]:
        """Pick up to ``size`` (provider, model) pairs, one per provider.

        Uses the scoring engine's ranking so the council draws from the same
        pool as normal routing, but deduplicates by provider: two models from
        one vendor would not add an independent opinion.
        """
        scored = []
        try:
            intent = self._chain._scoring.analyze_intent(query)
            scored = self._chain._scoring.score_models(query, intent, available)
        except Exception as exc:  # noqa: BLE001 - scoring is an optimisation, not a gate
            logger.warning(f"scoring unavailable for council: {exc}")

        picked: list[tuple[str, str]] = []
        seen: set[str] = set()
        for model in scored:
            if model.provider in seen:
                continue
            seen.add(model.provider)
            picked.append((model.provider, model.model_name))
            if len(picked) >= size:
                break

        # Fill any shortfall with providers the scorer did not rank.
        for provider in available:
            if len(picked) >= size:
                break
            if provider in seen:
                continue
            seen.add(provider)
            obj = self._chain._providers.get(provider)
            if obj is not None:
                picked.append((provider, obj.get_default_model()))
        return picked[:size]

    async def _ask(self, provider: str, model: str, messages: list[dict[str, str]],
                   temperature: float, max_tokens: int) -> CouncilMember:
        """Ask one member. A failure is recorded, never raised."""
        member = CouncilMember(provider=provider, model=model)
        obj = self._chain._providers.get(provider)
        if obj is None or not obj.is_configured():
            member.error = "not configured"
            return member
        if not obj.should_use():
            member.error = "circuit open"
            return member

        start = time.monotonic()
        try:
            model_to_use = self._chain._map_model_to_provider(model, provider, obj)
            response = await obj.generate(
                AIRequest(messages=messages, model=model_to_use, temperature=temperature, max_tokens=max_tokens)
            )
            member.model = model_to_use
            member.content = response.content or ""
            member.latency_ms = int((time.monotonic() - start) * 1000)
        except Exception as exc:  # noqa: BLE001 - one member failing is expected
            member.error = f"{type(exc).__name__}: {str(exc)[:120]}"
            member.latency_ms = int((time.monotonic() - start) * 1000)
        return member

    async def _score_members(self, members: list[CouncilMember], intent: str) -> None:
        """Fill in each member's quality score, concurrently."""
        criteria = ["correctness", "completeness", "clarity"]

        async def one(member: CouncilMember) -> None:
            try:
                member.score = await self._judge.judge(member.content, criteria, intent=intent)
            except Exception:  # noqa: BLE001 - an unjudgeable answer scores 0
                member.score = 0.0

        await asyncio.gather(*(one(m) for m in members if m.ok))

    @staticmethod
    def _consensus_for(members: list[CouncilMember], winner: CouncilMember) -> float:
        """Fraction of members whose answer broadly matches the winner."""
        if len(members) <= 1:
            return 1.0
        agree = sum(1 for m in members if answer_similarity(m.content, winner.content) >= 0.5)
        return agree / len(members)

    def _vote(self, members: list[CouncilMember]) -> CouncilMember:
        """Return the member most similar to all the others (the centroid)."""
        best, best_total = members[0], -1.0
        for candidate in members:
            total = sum(answer_similarity(candidate.content, other.content) for other in members if other is not candidate)
            if total > best_total:
                best, best_total = candidate, total
        return best

    async def _synthesize(self, chair: CouncilMember, members: list[CouncilMember],
                          messages: list[dict[str, str]], temperature: float,
                          max_tokens: int) -> CouncilMember | None:
        """Ask the strongest member to merge the others into one answer."""
        others = [m for m in members if m is not chair and m.ok]
        if not others:
            return None
        original = messages[-1]["content"] if messages else ""
        digest = "\n\n".join(f"[{m.provider}/{m.model}]\n{m.content}" for m in others)
        prompt = (
            "Several AI models answered the question below. Merge their answers into one "
            "reply that is complete and free of contradictions. Keep any point only one "
            "model caught. Do not mention the models.\n\n"
            f"Question:\n{original}\n\nModel answers:\n{digest}"
        )
        member = await self._ask(
            chair.provider, chair.model,
            [{"role": "user", "content": prompt}],
            temperature, max_tokens,
        )
        return member if member.ok else None

    async def deliberate(self, messages: list[dict[str, str]], user_input: str = None,
                         strategy: CouncilStrategy = CouncilStrategy.BEST, size: int = 3,
                         temperature: float = 0.7, max_tokens: int = 1000) -> CouncilResult:
        """Run one deliberation and return the reconciled answer."""
        start = time.monotonic()
        query = user_input or (messages[-1]["content"] if messages else "")
        available = self._chain.get_available_providers()
        if not available:
            return CouncilResult(False, strategy, error="No AI providers configured.")

        candidates = self._pick_candidates(query, available, max(1, size))
        members = list(await asyncio.gather(
            *(self._ask(p, m, messages, temperature, max_tokens) for p, m in candidates)
        ))
        ok = [m for m in members if m.ok]
        if not ok:
            errors = "; ".join(f"{m.provider}: {m.error}" for m in members)
            return CouncilResult(False, strategy, members=members,
                                 error=f"All council members failed: {errors}")

        winner: CouncilMember
        answer: str
        if strategy is CouncilStrategy.VOTE:
            winner = self._vote(ok)
            answer = winner.content
        elif strategy is CouncilStrategy.SYNTHESIS:
            await self._score_members(ok, query)
            chair = max(ok, key=lambda m: m.score)
            merged = await self._synthesize(chair, ok, messages, temperature, max_tokens)
            winner = merged or chair
            answer = winner.content
        else:  # BEST
            await self._score_members(ok, query)
            winner = max(ok, key=lambda m: m.score)
            answer = winner.content

        consensus = self._consensus_for(ok, winner) if strategy is not CouncilStrategy.SYNTHESIS else 0.0
        total = int((time.monotonic() - start) * 1000)
        logger.info(f"Council ({strategy.value}) answered by {winner.provider}/{winner.model} "
                    f"in {total}ms; {len(ok)}/{len(members)} members ok")
        return CouncilResult(True, strategy, answer=answer, winner=winner, members=members,
                             consensus=consensus, total_latency_ms=total)


_COUNCIL: LLMCouncil | None = None


def get_council() -> LLMCouncil:
    """Return the process-wide council instance."""
    global _COUNCIL
    if _COUNCIL is None:
        _COUNCIL = LLMCouncil()
    return _COUNCIL
