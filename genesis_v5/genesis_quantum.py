#!/usr/bin/env python3
"""Run real quantum algorithms and see the results.

    python3 genesis_quantum.py

Each algorithm is genuine quantum mechanics on a full complex statevector:
Grover's search, the Quantum Fourier Transform, Deutsch-Jozsa, and a CHSH Bell
test that beats the classical limit. Standard library only.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.quantum.algorithms import (
    chsh_test,
    deutsch_jozsa,
    grover_search,
    quantum_fourier_transform,
)


def _header(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> int:
    _header("GROVER'S SEARCH - find 1 item among 16 with ~3 queries")
    g = grover_search(4, [10], shots=2000, seed=7)
    print(f"  search space     : {g.detail['search_space']} states")
    print(f"  marked item      : {g.detail['marked']}  (binary {g.outcome})")
    print(f"  iterations       : {g.detail['iterations']}  (classical worst case: 16)")
    print(f"  theory P(marked) : {g.ideal_probability:.4f}")
    print(f"  measured         : {g.measured_frequency:.4f}")
    print(f"  found            : {int(g.outcome, 2)}  {'CORRECT' if int(g.outcome, 2) == 10 else 'WRONG'}")

    _header("QUANTUM FOURIER TRANSFORM - uniform phase spread")
    q = quantum_fourier_transform(4, input_basis=1)
    print(f"  input            : |{1}>")
    print(f"  output           : {q.outcome}")
    print(f"  |amplitude|      : {q.detail['magnitude']}  (should be 1/sqrt(16) = 0.25)")
    print(f"  all equal        : {q.detail['amplitudes_uniform_magnitude']}")

    _header("DEUTSCH-JOZSA - constant or balanced, in one query")
    bal = deutsch_jozsa(3, lambda x, n: bin(x).count("1") % 2, shots=1000, seed=3)
    con = deutsch_jozsa(3, lambda x, n: 0, shots=1000, seed=3)
    print(f"  balanced function: verdict={bal.outcome}  P(|000>)={bal.ideal_probability:.4f}")
    print(f"  constant function: verdict={con.outcome}  P(|000>)={con.ideal_probability:.4f}")
    print("  (a classical computer needs 2^(n-1)+1 = 5 queries; quantum needs 1)")

    _header("CHSH BELL TEST - a limit no classical theory can break")
    c = chsh_test(shots=4000, seed=11)
    print(f"  classical bound  : {c.detail['classical_bound']}")
    print(f"  quantum bound    : {c.detail['quantum_bound']}")
    print(f"  measured S       : {c.measured_frequency:.4f}")
    print(f"  violates classical: {c.detail['violates_classical']}")
    print("  (this is real non-locality, computed from complex amplitudes)")

    print("\n" + "=" * 68)
    print("All results computed from a genuine complex-amplitude statevector.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
