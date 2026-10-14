"""Tests for parallel generation: many proposals, no execution."""
from __future__ import annotations

from genesis.generation.generator import ParallelGenerator


def test_generator_produces_all_branches() -> None:
    result = ParallelGenerator(seed=1).generate("design a caching layer", shots=128)
    names = {b.name for b in result.branches}
    assert names == {"structural_synthesis", "latent_inversion", "direct_execution"}


def test_branches_carry_the_raw_input_unfiltered() -> None:
    raw = "  weird!! input @#$ with no cleanup  "
    result = ParallelGenerator(seed=1).generate(raw, shots=64)
    assert result.raw_input == raw
    assert all(raw in b.proposal for b in result.branches)


def test_generation_never_claims_execution_authority() -> None:
    result = ParallelGenerator(seed=1).generate("do something", shots=64)
    assert result.requires_authority is True
    for branch in result.branches:
        assert "execution_trigger" not in branch.to_dict()
        assert "bypass_gatekeeper" not in branch.to_dict()


def test_quantum_weights_are_probabilities() -> None:
    result = ParallelGenerator(seed=2).generate("x", shots=256)
    total = sum(b.quantum_weight for b in result.branches)
    assert 0.0 <= total <= 1.0
    for branch in result.branches:
        assert 0.0 <= branch.quantum_weight <= 1.0
        assert 0.0 < branch.confidence <= 1.0


def test_sampling_is_genuinely_varied_across_runs() -> None:
    first = ParallelGenerator(seed=10).generate("x", shots=128)
    second = ParallelGenerator(seed=11).generate("x", shots=128)
    w1 = {b.name: b.quantum_weight for b in first.branches}
    w2 = {b.name: b.quantum_weight for b in second.branches}
    assert w1 != w2


def test_ranked_orders_by_quantum_weight() -> None:
    result = ParallelGenerator(seed=4).generate("x", shots=256)
    ranked = result.ranked()
    weights = [b.quantum_weight for b in ranked]
    assert weights == sorted(weights, reverse=True)
