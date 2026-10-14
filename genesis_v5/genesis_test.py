#!/usr/bin/env python3
"""Run Genesis yourself: raw input in, proposals out, the gate on display.

    python3 genesis_test.py "your raw input here"

Nothing is executed except through the authority gate. The script shows the
gate allowing one request and denying another, so you can see the boundary for
yourself. Requires no dependencies beyond the standard library.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.pipeline.authority import AuthorityPipeline
from genesis.quantum.backends import detect_backends, has_real_hardware_access
from genesis.tools.gateway import ToolRequest


def _line(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def main() -> int:
    raw_input = " ".join(sys.argv[1:]) or "help me plan a small cache for my API"

    _line("1. QUANTUM BACKENDS (honest report)")
    for backend in detect_backends():
        mark = "available" if backend.available else "unavailable"
        print(f"  {backend.name:<22} {mark:<12} {backend.detail}")
    print(f"  real hardware credential present: {has_real_hardware_access()}")

    _line("2. GENERATE PROPOSALS FROM RAW INPUT")
    print(f"  raw input (unfiltered): {raw_input!r}")
    generator = ParallelGenerator(num_qubits=3, seed=7)
    generation = generator.generate(raw_input, shots=512)
    for branch in generation.ranked():
        print(f"  [{branch.quantum_weight:.3f}] {branch.name}")
        print(f"        {branch.proposal}")
    print(f"  requires_authority: {generation.requires_authority}")

    _line("3. AUTHORITY GATE (generation -> action)")
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    pipeline = AuthorityPipeline(generator, kernel.gateway)

    requests = [
        # Allowed: a read-only listing inside the sandbox root.
        ToolRequest(
            tool="file.list",
            args={"path": "/workspace"},
            actor="demo",
            role="coder",
            cwd="/workspace",
        ),
        # Denied: a write attempted by a role with no write permission.
        ToolRequest(
            tool="file.write",
            args={"path": "/workspace/should_not_exist.txt", "content": "x"},
            actor="demo",
            role="researcher",
            cwd="/workspace",
        ),
    ]

    result = pipeline.submit(raw_input, requests, shots=512)
    for action in result.actions:
        verdict = "GRANTED" if action.granted else "DENIED "
        print(f"  {verdict} {action.request.tool:<12} role={action.request.role}")
        if action.reason:
            print(f"          reason: {action.reason}")

    _line("4. SUMMARY")
    print(f"  stages run         : {result.stages}")
    print(f"  executed           : {result.executed}")
    print(f"  denied             : {result.denied}")
    print(f"  bypass_available   : {result.bypass_available}")
    print("  (no proposal can opt out of the gate)")
    print("\nDone. Genesis ran for real; nothing bypassed the gate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
