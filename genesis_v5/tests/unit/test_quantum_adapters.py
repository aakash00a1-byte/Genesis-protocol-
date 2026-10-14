"""Tests for quantum adapters: honest about what is actually installed."""
from __future__ import annotations

from genesis.quantum.adapters import (
    PennyLaneAdapter,
    QiskitAdapter,
    available_adapters,
)


def test_qiskit_adapter_reports_unavailable_when_missing() -> None:
    adapter = QiskitAdapter()
    if adapter.available():
        result = adapter.run_bell(shots=64)
        assert result.kind in ("simulator", "hardware")
        assert set(result.counts) <= {"00", "11"}
    else:
        result = adapter.run_bell(shots=64)
        assert result.kind == "unavailable"
        assert result.counts == {}


def test_pennylane_adapter_reports_unavailable_when_missing() -> None:
    adapter = PennyLaneAdapter()
    result = adapter.run_bell(shots=64)
    if adapter.available():
        assert result.kind == "simulator"
    else:
        assert result.kind == "unavailable"


def test_available_adapters_is_honest() -> None:
    # Neither library is installed in this offline environment.
    assert available_adapters() == []
