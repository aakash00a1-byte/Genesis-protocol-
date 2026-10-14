"""Real quantum state simulation and optional hardware backends.

This is genuine quantum linear algebra, not a metaphor: the built-in simulator
keeps the full complex statevector and applies real unitary gates. It states
plainly when it is simulating rather than running on hardware.
"""

from genesis.quantum.backends import (
    BackendInfo,
    detect_backends,
    has_real_hardware_access,
)
from genesis.quantum.simulator import (
    GATES,
    Measurement,
    QuantumRegister,
    bell_state,
    hadamard_all,
    uniform_superposition,
)

__all__ = [
    "BackendInfo",
    "GATES",
    "Measurement",
    "QuantumRegister",
    "bell_state",
    "detect_backends",
    "hadamard_all",
    "has_real_hardware_access",
    "uniform_superposition",
]
