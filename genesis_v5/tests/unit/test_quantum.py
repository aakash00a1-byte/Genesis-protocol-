"""Tests for the real quantum simulator: genuine linear algebra, not metaphor."""
from __future__ import annotations

import math

import pytest

from genesis.quantum.backends import detect_backends, has_real_hardware_access
from genesis.quantum.simulator import (
    H,
    QuantumRegister,
    bell_state,
    uniform_superposition,
)


def test_register_starts_in_ground_state() -> None:
    register = QuantumRegister(2)
    assert register.amplitudes()[0] == 1 + 0j
    assert register.probabilities() == [1.0, 0.0, 0.0, 0.0]


def test_x_gate_flips_a_qubit() -> None:
    register = QuantumRegister(1)
    register.apply_gate("X", 0)
    assert register.probabilities() == [0.0, 1.0]


def test_hadamard_creates_a_real_superposition() -> None:
    register = QuantumRegister(1)
    register.apply_gate(H, 0)
    probs = register.probabilities()
    assert probs[0] == pytest.approx(0.5)
    assert probs[1] == pytest.approx(0.5)


def test_amplitudes_are_normalised_after_evolution() -> None:
    register = QuantumRegister(3)
    for qubit in range(3):
        register.apply_gate(H, qubit)
    total = sum(register.probabilities())
    assert total == pytest.approx(1.0)


def test_bell_state_is_entangled() -> None:
    register = bell_state(seed=7)
    # (|00> + |11>)/sqrt(2): only those two outcomes are possible.
    probs = register.probabilities()
    assert probs[0] == pytest.approx(0.5)
    assert probs[3] == pytest.approx(0.5)
    assert probs[1] == pytest.approx(0.0)
    assert probs[2] == pytest.approx(0.0)


def test_bell_measurements_are_perfectly_correlated() -> None:
    register = bell_state(seed=1)
    outcomes = register.sample(shots=200)
    assert all(o in (0b00, 0b11) for o in outcomes)
    # Both outcomes should appear across a reasonable sample.
    assert set(outcomes) == {0b00, 0b11}


def test_measurement_collapses_to_a_single_basis_state() -> None:
    register = uniform_superposition(3, seed=3)
    result = register.measure()
    collapsed = register.amplitudes()
    non_zero = [i for i, a in enumerate(collapsed) if abs(a) > 1e-12]
    assert non_zero == [result.outcome]
    assert result.bits == [
        (result.outcome >> q) & 1 for q in range(3)
    ]


def test_uniform_superposition_samples_all_outcomes() -> None:
    register = uniform_superposition(3, seed=5)
    outcomes = set(register.sample(shots=400))
    assert outcomes == set(range(8))


def test_controlled_gate_only_fires_on_one() -> None:
    register = QuantumRegister(2)
    register.cnot(0, 1)
    # control is 0, so nothing changes
    assert register.probabilities()[0] == pytest.approx(1.0)
    register.apply_gate("X", 0)
    register.cnot(0, 1)
    assert register.probabilities()[3] == pytest.approx(1.0)


def test_backends_report_the_truth_about_availability() -> None:
    backends = detect_backends()
    builtin = next(b for b in backends if b.name == "builtin-statevector")
    assert builtin.available is True
    # qiskit is not installed in this environment; the report must say so.
    qiskit = next(b for b in backends if b.name == "qiskit")
    assert qiskit.available is False
    assert qiskit.kind == "unavailable"


def test_hardware_access_requires_a_credential() -> None:
    # No IBM token is set here, so the system is simulating and says so.
    assert has_real_hardware_access() is False
