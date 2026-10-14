"""Tests for Grover-based candidate ranking."""
from __future__ import annotations

from genesis.generation.generator import ParallelGenerator
from genesis.generation.quantum_rank import rank_candidates


def test_rank_candidates_amplifies_marked_items() -> None:
    candidates = [f"c{i}" for i in range(16)]
    result = rank_candidates(candidates, lambda c: c == "c7", shots=1024, seed=3)
    assert result.ranked[0].candidate == "c7"
    assert result.ranked[0].marked is True
    # Marked set is amplified far above the unmarked baseline of 1/16.
    assert result.ranked[0].amplified_weight > 0.8
    assert result.ideal_marked_probability > 0.9


def test_rank_candidates_with_no_marked_items_is_uniform() -> None:
    candidates = [f"c{i}" for i in range(8)]
    result = rank_candidates(candidates, lambda c: False, shots=256, seed=1)
    weights = {round(r.amplified_weight, 6) for r in result.ranked}
    assert weights == {round(1 / 8, 6)}
    assert result.iterations == 0


def test_generator_uses_grover_when_quality_given() -> None:
    gen = ParallelGenerator(seed=5)
    result = gen.generate(
        "design a cache",
        shots=256,
        quality=lambda p: "architecture" in p,
    )
    assert result.quantum_backend == "builtin-statevector+grover"
    assert result.branches[0].source == "generator+grover"
    # structural_synthesis is the branch containing "architecture".
    assert result.ranked()[0].name == "structural_synthesis"


def test_generator_default_path_unchanged() -> None:
    gen = ParallelGenerator(seed=5)
    result = gen.generate("design a cache", shots=64)
    assert result.quantum_backend == "builtin-statevector"
    assert all(b.source == "generator" for b in result.branches)
