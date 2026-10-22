#!/usr/bin/env python3
"""Let Genesis look at itself and propose improvements.

    python3 genesis_evolve.py            # one observation cycle
    python3 genesis_evolve.py --loop      # observe every --interval seconds
    python3 genesis_evolve.py --json      # machine-readable report

The agent observes the system's own recent behaviour (failures, denials,
unresolved decisions) and writes a small, ranked, review-gated backlog of
proposals. It changes nothing: no edits, no deploys, no merges. Every proposal
is marked ``requires_review`` and ``requires_authority``. A human decides.

Standard library only. Offline by default.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.core import MemoryScope
from genesis.kernel.kernel import KernelRequest


def _run_cycle(kernel, *, as_json: bool) -> int:
    agent = kernel.evolution
    if agent is None:
        print("evolution agent is not enabled (set config.evolution.enabled)", file=sys.stderr)
        return 2
    report = agent.observe()
    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0

    counts = report.counts
    print(f"cycle {report.cycle_id}  verdict={report.verdict}")
    print(
        f"  signals: {counts.get('weakness', 0)} weakness, "
        f"{counts.get('health', 0)} health, "
        f"{counts.get('improvement', 0)} opportunity"
    )
    ranked = report.rank()
    if not ranked:
        print("  no proposals — nothing to improve right now.")
    else:
        print(f"  {len(ranked)} proposal(s), highest priority first:")
        for index, proposal in enumerate(ranked, start=1):
            print(f"    {index}. [{proposal.priority:.2f}] {proposal.title}")
            if proposal.rationale:
                print(f"       why: {proposal.rationale}")
    for note in report.notes:
        print(f"  note: {note}")
    print("  (review-gated: nothing is changed automatically)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genesis self-observation cycle")
    parser.add_argument("--loop", action="store_true", help="keep observing")
    parser.add_argument("--interval", type=float, default=3600.0, help="seconds between cycles")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument(
        "--via-pipeline",
        action="store_true",
        help="also route a self-improve task through the full Kernel pipeline",
    )
    args = parser.parse_args(argv)

    cfg = GenesisConfig(env=Env.DEVELOPMENT, offline=True)
    cfg.evolution.enabled = True
    kernel = build(cfg)

    if args.via_pipeline:
        response = kernel.run(
            KernelRequest(
                task="self-improve: observe the system and propose improvements",
                actor="operator",
                role="admin",
                scope=MemoryScope.PROJECT,
            )
        )
        print("pipeline ok:", response.ok, "| result:", str(response.result)[:200])

    if not args.loop:
        return _run_cycle(kernel, as_json=args.json)

    print(f"observing every {args.interval:.0f}s — Ctrl+C to stop")
    try:
        while True:
            _run_cycle(kernel, as_json=args.json)
            time.sleep(max(1.0, args.interval))
    except KeyboardInterrupt:
        print("\nstopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
