"""Real quantum state simulation — pure Python, no dependencies.

This is a genuine statevector simulator, not a metaphor. It keeps the full
complex amplitude vector of an ``n``-qubit register and applies unitary gates
as complex linear algebra. Measurement samples from the Born probabilities and
collapses the state, exactly as quantum mechanics prescribes.

It runs offline with only the standard library, so it works in the same
zero-dependency environment as the rest of Genesis. A Qiskit or PennyLane
backend can be attached through ``genesis.quantum.backends`` when those
libraries are installed.

Complex numbers are represented as ``(real, imag)`` tuples to keep the core
dependency-free.
"""
from __future__ import annotations

import cmath
import math
import random
from dataclasses import dataclass
from typing import Any, Callable

Amplitude = complex
Vector = list[complex]

# Gates expressed as 2x2 complex matrices over (a, b, c, d).
Gate2 = tuple[complex, complex, complex, complex]

I2: Gate2 = (1, 0, 0, 1)
X: Gate2 = (0, 1, 1, 0)
Y: Gate2 = (0, -1j, 1j, 0)
Z: Gate2 = (1, 0, 0, -1)
H: Gate2 = (
    1 / math.sqrt(2),
    1 / math.sqrt(2),
    1 / math.sqrt(2),
    -1 / math.sqrt(2),
)
S: Gate2 = (1, 0, 0, 1j)
T: Gate2 = (1, 0, 0, cmath.exp(1j * math.pi / 4))

GATES: dict[str, Gate2] = {
    "I": I2,
    "X": X,
    "Y": Y,
    "Z": Z,
    "H": H,
    "S": S,
    "T": T,
}


@dataclass
class Measurement:
    """Outcome of measuring a qubit register."""

    outcome: int
    bits: list[int]
    probability: float
    collapsed_state: Vector

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "bits": list(self.bits),
            "probability": self.probability,
        }


class QuantumRegister:
    """An n-qubit statevector register with real unitary evolution."""

    def __init__(self, num_qubits: int, *, seed: int | None = None) -> None:
        if num_qubits < 1:
            raise ValueError("a register needs at least one qubit")
        self.num_qubits = num_qubits
        self._rng = random.Random(seed)
        self._state: Vector = [0j] * (1 << num_qubits)
        self._state[0] = 1 + 0j  # |00...0>

    # ------------------------------------------------------------------
    @property
    def size(self) -> int:
        return 1 << self.num_qubits

    def amplitudes(self) -> Vector:
        return list(self._state)

    def probabilities(self) -> list[float]:
        return [abs(a) ** 2 for a in self._state]

    # ------------------------------------------------------------------
    def apply_gate(self, gate: str | Gate2, target: int) -> "QuantumRegister":
        """Apply a single-qubit gate to ``target``."""
        matrix = GATES[gate] if isinstance(gate, str) else gate
        if not 0 <= target < self.num_qubits:
            raise ValueError(f"target qubit {target} out of range")
        a, b, c, d = matrix
        step = 1 << target
        new = list(self._state)
        for base in range(0, self.size, step << 1):
            for offset in range(step):
                i0 = base + offset
                i1 = i0 + step
                x0, x1 = self._state[i0], self._state[i1]
                new[i0] = a * x0 + b * x1
                new[i1] = c * x0 + d * x1
        self._state = new
        return self

    def apply_controlled(
        self, gate: str | Gate2, control: int, target: int
    ) -> "QuantumRegister":
        """Apply a single-qubit gate to ``target`` when ``control`` is 1."""
        if control == target:
            raise ValueError("control and target must differ")
        matrix = GATES[gate] if isinstance(gate, str) else gate
        a, b, c, d = matrix
        step = 1 << target
        cbit = 1 << control
        new = list(self._state)
        for base in range(0, self.size, step << 1):
            for offset in range(step):
                i0 = base + offset
                i1 = i0 + step
                if (i0 & cbit) == 0:
                    continue
                x0, x1 = self._state[i0], self._state[i1]
                new[i0] = a * x0 + b * x1
                new[i1] = c * x0 + d * x1
        self._state = new
        return self

    def cnot(self, control: int, target: int) -> "QuantumRegister":
        return self.apply_controlled(X, control, target)

    def measure(self) -> Measurement:
        """Sample one outcome by Born's rule and collapse the state."""
        probs = self.probabilities()
        total = sum(probs)
        if total <= 0:
            raise ValueError("cannot measure a zero state")
        pick = self._rng.random() * total
        acc = 0.0
        outcome = len(probs) - 1
        for index, p in enumerate(probs):
            acc += p
            if pick <= acc:
                outcome = index
                break
        norm = math.sqrt(probs[outcome]) or 1.0
        collapsed = [0j] * self.size
        collapsed[outcome] = self._state[outcome] / norm
        self._state = collapsed
        bits = [(outcome >> q) & 1 for q in range(self.num_qubits)]
        return Measurement(
            outcome=outcome,
            bits=bits,
            probability=probs[outcome],
            collapsed_state=list(collapsed),
        )

    def sample(self, shots: int = 1) -> list[int]:
        """Measure ``shots`` times, restoring superposition between shots.

        The state is re-prepared from the amplitudes captured before the first
        collapse so every shot samples the same prepared state.
        """
        prepared = list(self._state)
        results: list[int] = []
        for _ in range(max(1, shots)):
            self._state = list(prepared)
            results.append(self.measure().outcome)
        self._state = list(prepared)
        return results


def hadamard_all(register: QuantumRegister) -> QuantumRegister:
    for qubit in range(register.num_qubits):
        register.apply_gate(H, qubit)
    return register


def uniform_superposition(num_qubits: int, *, seed: int | None = None) -> QuantumRegister:
    """Prepare (|0>+|1>)^n / sqrt(2^n): every basis state equally likely."""
    register = QuantumRegister(num_qubits, seed=seed)
    return hadamard_all(register)


def bell_state(*, seed: int | None = None) -> QuantumRegister:
    """Prepare the maximally entangled Bell state (|00>+|11>)/sqrt(2)."""
    register = QuantumRegister(2, seed=seed)
    register.apply_gate(H, 0)
    register.cnot(0, 1)
    return register
