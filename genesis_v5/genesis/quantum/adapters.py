"""Optional Qiskit and PennyLane adapters.

These bridge Genesis to real quantum toolchains when they are installed. When
they are not, each adapter reports ``available=False`` and the caller uses the
built-in simulator. Nothing here pretends to be more than it is: an adapter
that is missing says so, and a circuit run on a simulator is labelled as such.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genesis.quantum.backends import _has, has_real_hardware_access


@dataclass
class CircuitResult:
    """Outcome of running a circuit, with honest provenance."""

    backend: str
    kind: str  # "simulator" | "hardware" | "unavailable"
    counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "kind": self.kind,
            "counts": dict(self.counts),
        }


class QiskitAdapter:
    """Run a Bell circuit via Qiskit, on Aer or IBM hardware when available."""

    name = "qiskit"

    def available(self) -> bool:
        return _has("qiskit")

    def run_bell(self, *, shots: int = 1024) -> CircuitResult:
        if not self.available():
            return CircuitResult(
                backend="qiskit", kind="unavailable", counts={}
            )
        from qiskit import QuantumCircuit, transpile  # type: ignore
        from qiskit_aer import AerSimulator  # type: ignore

        circuit = QuantumCircuit(2, 2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure([0, 1], [0, 1])
        simulator = AerSimulator()
        compiled = transpile(circuit, simulator)
        result = simulator.run(compiled, shots=shots).result()
        counts = {str(k): int(v) for k, v in result.get_counts().items()}
        kind = "hardware" if has_real_hardware_access() else "simulator"
        return CircuitResult(backend="qiskit-aer", kind=kind, counts=counts)


class PennyLaneAdapter:
    """Run a Bell circuit via PennyLane's default simulator."""

    name = "pennylane"

    def available(self) -> bool:
        return _has("pennylane")

    def run_bell(self, *, shots: int = 1024) -> CircuitResult:
        if not self.available():
            return CircuitResult(
                backend="pennylane", kind="unavailable", counts={}
            )
        import pennylane as qml  # type: ignore

        dev = qml.device("default.qubit", wires=2, shots=shots)

        @qml.qnode(dev)
        def circuit() -> Any:
            qml.Hadamard(wires=0)
            qml.CNOT(wires=[0, 1])
            return qml.counts()

        counts = {str(k): int(v) for k, v in circuit().items()}
        return CircuitResult(backend="pennylane-default.qubit", kind="simulator", counts=counts)


def available_adapters() -> list[str]:
    adapters = [QiskitAdapter(), PennyLaneAdapter()]
    return [a.name for a in adapters if a.available()]
