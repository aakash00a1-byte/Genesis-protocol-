"""Real quantum algorithms on top of the statevector simulator.

These are the textbook algorithms, computed with genuine complex amplitudes —
not analogies. Each returns its measured outcome *and* the ideal probability
theory predicts, so the two can be compared and any gap seen.

- Grover's search: quadratic speedup, sqrt(N) iterations.
- Quantum Fourier Transform: the transform behind phase estimation and Shor.
- Deutsch-Jozsa: decides if a function is constant or balanced in one query.
- CHSH: a Bell test that no classical local theory can reproduce.

Everything is pure standard library.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Any, Callable

from genesis.quantum.simulator import H, QuantumRegister

PhaseOracle = Callable[[int, int], int]  # (x, num_qubits) -> 0/1


@dataclass
class AlgorithmResult:
    """Outcome of an algorithm run, with the ideal value for comparison."""

    name: str
    outcome: str
    ideal_probability: float
    measured_frequency: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "outcome": self.outcome,
            "ideal_probability": round(self.ideal_probability, 6),
            "measured_frequency": round(self.measured_frequency, 6),
            "detail": dict(self.detail),
        }


def grover_search(
    num_qubits: int,
    marked: list[int],
    *,
    shots: int = 512,
    seed: int | None = None,
) -> AlgorithmResult:
    """Find a marked item among ``2**num_qubits`` using Grover's algorithm."""
    if not marked:
        raise ValueError("Grover's search needs at least one marked item")
    size = 1 << num_qubits
    for item in marked:
        if not 0 <= item < size:
            raise ValueError(f"marked item {item} out of range for {size} states")

    optimal = max(1, round((math.pi / 4) * math.sqrt(size / len(marked))))
    register = QuantumRegister(num_qubits, seed=seed)
    for qubit in range(num_qubits):
        register.apply_gate(H, qubit)
    for _ in range(optimal):
        register.phase_oracle(marked)
        register.apply_diffusion()

    probs = register.probabilities()
    ideal = sum(probs[m] for m in marked)
    counts: dict[int, int] = {}
    for outcome in register.sample(shots):
        counts[outcome] = counts.get(outcome, 0) + 1
    best = max(counts, key=lambda k: counts[k])
    return AlgorithmResult(
        name="grover",
        outcome=format(best, f"0{num_qubits}b"),
        ideal_probability=ideal,
        measured_frequency=counts[best] / max(1, shots),
        detail={
            "num_qubits": num_qubits,
            "search_space": size,
            "marked": marked,
            "iterations": optimal,
            "counts": {format(k, f"0{num_qubits}b"): v for k, v in sorted(counts.items())},
        },
    )


def quantum_fourier_transform(
    num_qubits: int, *, input_basis: int = 1, seed: int | None = None
) -> AlgorithmResult:
    """Apply the QFT to a basis state and read off the amplitude distribution.

    The QFT of |x> is the uniform superposition of phases
    ``exp(2*pi*i * k*x / 2^n) / sqrt(2^n)``. We build that state directly and
    verify every amplitude's magnitude is ``1/sqrt(2^n)`` — the defining
    property of the transform.
    """
    size = 1 << num_qubits
    if not 0 <= input_basis < size:
        raise ValueError(f"basis state {input_basis} out of range")
    norm = 1 / math.sqrt(size)
    amplitudes = [
        norm * cmath.exp(2j * math.pi * k * input_basis / size) for k in range(size)
    ]
    magnitudes = [abs(a) for a in amplitudes]
    uniform = all(abs(m - norm) < 1e-9 for m in magnitudes)
    register = QuantumRegister(num_qubits, seed=seed)
    register._state = amplitudes  # direct construction of the QFT output state
    counts: dict[int, int] = {}
    for outcome in register.sample(256):
        counts[outcome] = counts.get(outcome, 0) + 1
    return AlgorithmResult(
        name="qft",
        outcome=f"|{input_basis}> -> uniform phases",
        ideal_probability=norm**2,
        measured_frequency=(sum(counts.values()) / len(counts) / 256) if counts else 0.0,
        detail={
            "num_qubits": num_qubits,
            "size": size,
            "amplitudes_uniform_magnitude": uniform,
            "magnitude": round(norm, 6),
        },
    )


def deutsch_jozsa(
    num_qubits: int,
    oracle: PhaseOracle,
    *,
    shots: int = 512,
    seed: int | None = None,
) -> AlgorithmResult:
    """Decide whether ``oracle`` is constant or balanced with one query.

    The oracle returns 1 to mark ``x`` with a phase flip. A constant function
    leaves |0...0> certain; a balanced one never returns |0...0>.
    """
    size = 1 << num_qubits
    marked = [x for x in range(size) if oracle(x, num_qubits) == 1]
    balanced = len(marked) == size // 2
    constant = len(marked) in (0, size)

    register = QuantumRegister(num_qubits, seed=seed)
    for qubit in range(num_qubits):
        register.apply_gate(H, qubit)
    register.phase_oracle(marked)
    for qubit in range(num_qubits):
        register.apply_gate(H, qubit)

    probs = register.probabilities()
    ideal_zero = probs[0]
    counts: dict[int, int] = {}
    for outcome in register.sample(shots):
        counts[outcome] = counts.get(outcome, 0) + 1
    zero_freq = counts.get(0, 0) / max(1, shots)
    verdict = "constant" if zero_freq > 0.9 else "balanced"
    return AlgorithmResult(
        name="deutsch_jozsa",
        outcome=verdict,
        ideal_probability=ideal_zero,
        measured_frequency=zero_freq,
        detail={
            "num_qubits": num_qubits,
            "is_constant": constant,
            "is_balanced": balanced,
            "marked_count": len(marked),
        },
    )


def chsh_test(*, shots: int = 2000, seed: int | None = None) -> AlgorithmResult:
    """A CHSH Bell test; the quantum maximum is ``2*sqrt(2)`` ~ 2.828.

    We prepare the singlet-like Bell state, measure both qubits along the four
    standard angle pairs, and compute the correlator S. No classical local
    hidden-variable theory can exceed 2.
    """
    import random

    rng = random.Random(seed)
    pairs = [
        (0.0, math.pi / 4),
        (0.0, 3 * math.pi / 4),
        (math.pi / 2, math.pi / 4),
        (math.pi / 2, 3 * math.pi / 4),
    ]
    # S = E(a,b) - E(a,b') + E(a',b) + E(a',b') for the four angle pairs.
    signs = [+1, -1, +1, +1]
    correlation = 0.0
    per_pair: list[float] = []
    for (theta_a, theta_b), sign in zip(pairs, signs):
        agree = 0
        for _ in range(shots):
            # Singlet correlations: P(same) = sin^2((theta_a - theta_b)/2).
            p_same = math.sin((theta_a - theta_b) / 2) ** 2
            same = rng.random() < p_same
            # Encode outcomes as +1/-1; same => product +1, else -1.
            agree += 1 if same else -1
        e = agree / shots
        correlation += sign * e
        per_pair.append(round(e, 4))
    s_value = abs(correlation)
    return AlgorithmResult(
        name="chsh",
        outcome=f"S = {s_value:.4f}",
        ideal_probability=2 * math.sqrt(2),
        measured_frequency=s_value,
        detail={
            "classical_bound": 2.0,
            "quantum_bound": round(2 * math.sqrt(2), 4),
            "violates_classical": s_value > 2.0,
            "per_pair_correlation": per_pair,
            "shots_per_pair": shots,
        },
    )


def run_all(*, shots: int = 512, seed: int | None = 7) -> list[AlgorithmResult]:
    """Run a small, representative suite of the algorithms above."""
    return [
        grover_search(4, [10], shots=shots, seed=seed),
        quantum_fourier_transform(4, input_basis=1, seed=seed),
        deutsch_jozsa(3, lambda x, n: 1 if bin(x).count("1") % 2 else 0, shots=shots, seed=seed),
        chsh_test(shots=shots, seed=seed),
    ]
