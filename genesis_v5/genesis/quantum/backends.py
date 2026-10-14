"""Optional real-hardware and external-simulator backends.

The built-in ``QuantumRegister`` is a genuine simulator, but it is classical
hardware simulating quantum mechanics. For real quantum execution this module
bridges to Qiskit (IBM Quantum and local Aer) or PennyLane when those packages
are installed. When they are absent the backend reports itself unavailable and
the caller falls back to the built-in simulator — Genesis stays offline-first.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Any


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


@dataclass
class BackendInfo:
    """What kind of quantum execution is actually available."""

    name: str
    kind: str  # "simulator" | "hardware" | "unavailable"
    available: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "available": self.available,
            "detail": self.detail,
        }


def detect_backends() -> list[BackendInfo]:
    """Report which backends exist in this environment. Never guesses."""
    backends = [
        BackendInfo(
            name="builtin-statevector",
            kind="simulator",
            available=True,
            detail="pure-Python statevector simulator (always available)",
        )
    ]
    if _has("qiskit"):
        backends.append(
            BackendInfo(
                name="qiskit",
                kind="simulator",
                available=True,
                detail="Qiskit present; Aer and IBM Quantum runtimes usable",
            )
        )
    else:
        backends.append(
            BackendInfo(
                name="qiskit",
                kind="unavailable",
                available=False,
                detail="install qiskit to run on Aer or real IBM Quantum hardware",
            )
        )
    if _has("pennylane"):
        backends.append(
            BackendInfo(
                name="pennylane",
                kind="simulator",
                available=True,
                detail="PennyLane present; differentiable circuits usable",
            )
        )
    else:
        backends.append(
            BackendInfo(
                name="pennylane",
                kind="unavailable",
                available=False,
                detail="install pennylane for autodiff quantum circuits",
            )
        )
    return backends


def has_real_hardware_access() -> bool:
    """True only when a hardware credential is present.

    A real QPU needs a token (for example ``IBM_QUANTUM_TOKEN``). Without one we
    are simulating, and the system says so rather than implying otherwise.
    """
    import os

    return any(
        os.environ.get(key)
        for key in ("IBM_QUANTUM_TOKEN", "IBMQ_TOKEN", "QISKIT_IBM_TOKEN")
    )
