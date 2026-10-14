"""Grover amplitude amplification used to rank candidates.

This puts the quantum layer to work rather than leaving it as a demo. Given a
list of candidate strings and a classical quality predicate, it maps each
candidate to a basis state, marks the ones that satisfy the predicate, and runs
Grover iterations to amplify their amplitudes. The amplified probabilities
become the ranking weights.

Honest note on what this is and is not:

- It is a real amplitude-amplification computation on a complex statevector.
- It is *not* a speedup here. The quality predicate is classical and cheap, and
  we already know how many candidates there are. The value is that the ranking
  is produced by genuine quantum amplitude amplification, and that the result
  matches what theory predicts — the amplified probability of the marked set is
  reported alongside the measured value so any gap is visible.

A caller who wants a classical sort can ignore this module entirely.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from genesis.quantum.simulator import H, QuantumRegister

Quality = Callable[[str], bool]


@dataclass
class RankedCandidate:
    """A candidate with its Grover-amplified weight."""

    candidate: str
    index: int
    marked: bool
    amplified_weight: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "index": self.index,
            "marked": self.marked,
            "amplified_weight": round(self.amplified_weight, 6),
        }


@dataclass
class RankResult:
    ranked: list[RankedCandidate]
    iterations: int
    ideal_marked_probability: float
    measured_marked_probability: float
    num_qubits: int
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked": [r.to_dict() for r in self.ranked],
            "iterations": self.iterations,
            "ideal_marked_probability": round(self.ideal_marked_probability, 6),
            "measured_marked_probability": round(self.measured_marked_probability, 6),
            "num_qubits": self.num_qubits,
            "detail": dict(self.detail),
        }


def rank_candidates(
    candidates: list[str],
    quality: Quality,
    *,
    shots: int = 1024,
    seed: int | None = None,
) -> RankResult:
    """Rank candidates by Grover-amplified probability of being 'good'."""
    if not candidates:
        raise ValueError("no candidates to rank")
    size = len(candidates)
    num_qubits = max(1, math.ceil(math.log2(size))) if size > 1 else 1
    dim = 1 << num_qubits
    if size > dim:
        raise ValueError("candidate count exceeds register capacity")

    marked = [i for i, c in enumerate(candidates) if quality(c)]

    register = QuantumRegister(num_qubits, seed=seed)
    for qubit in range(num_qubits):
        register.apply_gate(H, qubit)

    if marked:
        # Standard Grover iteration count: floor(pi/4 * sqrt(N/M)). Using floor
        # rather than round matters for small registers, where one extra
        # iteration overshoots and returns the state toward uniform.
        iterations = max(1, math.floor((math.pi / 4) * math.sqrt(dim / len(marked))))
        for _ in range(iterations):
            register.phase_oracle(marked)
            register.apply_diffusion()
    else:
        iterations = 0

    probs = register.probabilities()
    ideal = sum(probs[m] for m in marked)
    measured_counts: dict[int, int] = {}
    for outcome in register.sample(shots):
        measured_counts[outcome] = measured_counts.get(outcome, 0) + 1
    measured_marked = (
        sum(v for k, v in measured_counts.items() if k in set(marked)) / max(1, shots)
        if marked
        else 0.0
    )

    ranked = [
        RankedCandidate(
            candidate=candidates[i],
            index=i,
            marked=i in set(marked),
            amplified_weight=probs[i],
        )
        for i in range(size)
    ]
    ranked.sort(key=lambda r: r.amplified_weight, reverse=True)
    return RankResult(
        ranked=ranked,
        iterations=iterations,
        ideal_marked_probability=ideal,
        measured_marked_probability=measured_marked,
        num_qubits=num_qubits,
        detail={"marked_count": len(marked), "register_size": dim},
    )
