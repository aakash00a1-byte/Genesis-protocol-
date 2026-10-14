#!/usr/bin/env python3
"""Talk to Genesis: a thought-partner in the terminal.

    python3 genesis_chat.py

Type anything. Genesis listens without judging, offers a few honest options,
and lets you choose. Type 'quit' to leave. Standard library only.

In a crisis it stops offering options and points to real human help. It is a
companion, not a therapist.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.bootstrap import build
from genesis.care.companion import CareCompanion, CareMode
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.reflection.partner import ThoughtPartner


def main() -> int:
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    partner = ThoughtPartner(
        CareCompanion(),
        ParallelGenerator(num_qubits=3),
        memory=kernel.memory,
    )

    print("Genesis thought-partner. Type 'quit' to leave.\n")
    while True:
        try:
            message = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0
        if message.lower() in {"quit", "exit", "bye"}:
            print("bye")
            return 0
        if not message:
            continue

        turn = partner.turn(message)
        print(f"\ngenesis> {turn.care.acknowledgement}")

        if turn.care.mode is CareMode.PROFESSIONAL_REFERRAL:
            print(f"genesis> {turn.care.next_step}")
            print(f"genesis> {turn.care.referral}")
            print(f"genesis> ({turn.care.resource_note})\n")
            continue

        print(f"genesis> {turn.care.next_step}")
        print("\n  options:")
        for index, option in enumerate(turn.options, start=1):
            print(f"    {index}. [{option.name}] {option.proposal}")
        print()

        pick = input("choose (number, or Enter to skip)> ").strip()
        if pick.isdigit() and 1 <= int(pick) <= len(turn.options):
            chosen = turn.options[int(pick) - 1].name
            partner.choose(turn.turn_id, chosen)
            print(f"  noted: you chose '{chosen}'. The choice is yours.\n")
        else:
            print()


if __name__ == "__main__":
    raise SystemExit(main())
