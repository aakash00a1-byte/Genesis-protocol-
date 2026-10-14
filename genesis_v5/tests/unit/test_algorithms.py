"""Tests for the real quantum algorithms: Grover, QFT, Deutsch-Jozsa, CHSH."""
from __future__ import annotations

import math

from genesis.quantum.algorithms import (
    AlgorithmResult,
    chsh_test,
    deutsch_jozsa,
    grover_search,
    quantum_fourier_transform,
    run_all,
)


def test_grover_finds_the_marked_item_with_high_probability() -> None:
    result = grover_search(4, [10], shots=1024, seed=7)
    assert result.outcome == format(10, "04b")
    # For a single marked item in 16, one iteration gives P ~ 0.96.
    assert result.ideal_probability > 0.9
    assert result.measured_frequency > 0.85


def test_grover_multiple_marked_items() -> None:
    result = grover_search(4, [3, 5], shots=1024, seed=1)
    assert result.ideal_probability > 0.9
    assert int(result.outcome, 2) in (3, 5)


def test_qft_amplitudes_are_uniform_in_magnitude() -> None:
    result = quantum_fourier_transform(4, input_basis=1)
    assert result.detail["amplitudes_uniform_magnitude"] is True
    assert abs(result.detail["magnitude"] - 1 / math.sqrt(16)) < 1e-9


def test_deutsch_jozsa_balanced_function() -> None:
    # Parity of the bit count is balanced for 3 qubits.
    result = deutsch_jozsa(3, lambda x, n: bin(x).count("1") % 2, shots=512, seed=3)
    assert result.outcome == "balanced"
    assert result.detail["is_balanced"] is True
    assert result.ideal_probability < 0.1


def test_deutsch_jozsa_constant_function() -> None:
    result = deutsch_jozsa(3, lambda x, n: 0, shots=512, seed=3)
    assert result.outcome == "constant"
    assert result.detail["is_constant"] is True
    assert result.ideal_probability > 0.99


def test_chsh_violates_the_classical_bound() -> None:
    result = chsh_test(shots=4000, seed=11)
    assert result.measured_frequency > 2.0  # beats the classical bound of 2
    assert result.detail["violates_classical"] is True
    assert result.measured_frequency <= 2 * math.sqrt(2) + 0.1


def test_run_all_returns_a_result_per_algorithm() -> None:
    results = run_all(shots=128, seed=5)
    assert len(results) == 4
    assert all(isinstance(r, AlgorithmResult) for r in results)
    assert {r.name for r in results} == {"grover", "qft", "deutsch_jozsa", "chsh"}
