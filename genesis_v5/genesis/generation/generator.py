"""Parallel generation of candidate branches from raw input.

This is the generative half of the system: given raw, unfiltered input it
produces several candidate proposals at once, each from a different angle. It
generates possibilities; it does not execute anything.

The three built-in strategies mirror the classic decomposition of a problem:

- ``structural_synthesis`` — build an architecture around the input
- ``latent_inversion``     — surface the unexpressed pattern underneath it
- ``direct_execution``     — translate it into an action blueprint

Branch weights come from real quantum sampling: a uniform superposition is
measured ``shots`` times and the observed frequencies weight the branches. This
gives genuinely probabilistic diversity rather than a fixed score.

Every result is a *proposal*. It carries ``requires_authority=True`` because
nothing here may act on its own — proposals must pass through the authority
layer (kernel policy, permissions, audit) before anything is executed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from genesis.core import new_id, now_ms
from genesis.quantum.simulator import uniform_superposition

Strategy = Callable[[str], str]


@dataclass
class Branch:
    """One candidate proposal generated from the raw input."""

    name: str
    proposal: str
    confidence: float
    quantum_weight: float
    branch_id: str = field(default_factory=lambda: new_id("br"))
    source: str = "generator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "name": self.name,
            "proposal": self.proposal,
            "confidence": round(self.confidence, 4),
            "quantum_weight": round(self.quantum_weight, 4),
            "source": self.source,
        }


@dataclass
class GenerationResult:
    """A set of proposals. Never an executable payload."""

    raw_input: str
    branches: list[Branch]
    quantum_backend: str
    shots: int
    requires_authority: bool = True
    generated_at_ms: int = field(default_factory=now_ms)

    def ranked(self) -> list[Branch]:
        return sorted(self.branches, key=lambda b: b.quantum_weight, reverse=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_input": self.raw_input,
            "branches": [b.to_dict() for b in self.branches],
            "ranked": [b.name for b in self.ranked()],
            "quantum_backend": self.quantum_backend,
            "shots": self.shots,
            "requires_authority": self.requires_authority,
            "generated_at_ms": self.generated_at_ms,
        }


def _structural_synthesis(raw_input: str) -> str:
    return f"Build an architecture around: {raw_input}"


def _latent_inversion(raw_input: str) -> str:
    return f"Surface the unexpressed pattern beneath: {raw_input}"


def _direct_execution(raw_input: str) -> str:
    return f"Draft an action blueprint for: {raw_input}"


DEFAULT_STRATEGIES: dict[str, Strategy] = {
    "structural_synthesis": _structural_synthesis,
    "latent_inversion": _latent_inversion,
    "direct_execution": _direct_execution,
}


class ParallelGenerator:
    """Generate candidate branches in parallel from raw input."""

    def __init__(
        self,
        strategies: dict[str, Strategy] | None = None,
        *,
        num_qubits: int = 3,
        seed: int | None = None,
    ) -> None:
        self.strategies = dict(strategies or DEFAULT_STRATEGIES)
        if not self.strategies:
            raise ValueError("at least one strategy is required")
        self.num_qubits = max(1, num_qubits)
        self.seed = seed

    def generate(
        self,
        raw_input: str,
        *,
        shots: int = 256,
        quality: Callable[[str], bool] | None = None,
    ) -> GenerationResult:
        """Produce weighted proposals for ``raw_input``.

        The input is accepted exactly as given — no sanitisation, no filtering.
        Only the *use* of the proposals is governed, by the authority layer.

        When ``quality`` is supplied, branch weights come from Grover amplitude
        amplification over the proposals (see ``genesis.generation.quantum_rank``)
        instead of plain uniform sampling.
        """
        shots = max(1, shots)
        names = list(self.strategies.keys())
        proposals = [self.strategies[name](raw_input) for name in names]

        if quality is not None:
            return self._generate_ranked(raw_input, names, proposals, quality, shots)

        register = uniform_superposition(self.num_qubits, seed=self.seed)
        outcomes = register.sample(shots=shots)
        counts: dict[int, int] = {}
        for outcome in outcomes:
            counts[outcome] = counts.get(outcome, 0) + 1

        branches: list[Branch] = []
        for index, name in enumerate(names):
            weight = counts.get(index % (1 << self.num_qubits), 0) / shots
            # Blend the quantum weight with a uniform prior so no branch is
            # starved to exactly zero by a short sampling run.
            confidence = 0.5 * weight + 0.5 * (1.0 / len(names))
            branches.append(
                Branch(
                    name=name,
                    proposal=proposals[index],
                    confidence=confidence,
                    quantum_weight=weight,
                )
            )

        return GenerationResult(
            raw_input=raw_input,
            branches=branches,
            quantum_backend="builtin-statevector",
            shots=shots,
        )

    def _generate_ranked(
        self,
        raw_input: str,
        names: list[str],
        proposals: list[str],
        quality: Callable[[str], bool],
        shots: int,
    ) -> GenerationResult:
        from genesis.generation.quantum_rank import rank_candidates

        result = rank_candidates(proposals, quality, shots=shots, seed=self.seed)
        by_index = {r.index: r for r in result.ranked}
        branches = [
            Branch(
                name=names[i],
                proposal=proposals[i],
                confidence=by_index[i].amplified_weight,
                quantum_weight=by_index[i].amplified_weight,
                source="generator+grover",
            )
            for i in range(len(names))
        ]
        return GenerationResult(
            raw_input=raw_input,
            branches=branches,
            quantum_backend="builtin-statevector+grover",
            shots=shots,
        )

