"""Append-only, hash-chained ledger for research records.

The ledger is the memory of the research engine. It exists because a research
process that can quietly delete its failures is not a research process: the
negative results are the ones that stop the same dead end being walked twice.

Entries are chained - each carries the hash of the previous entry - so an edit,
a deletion or a reorder is detectable rather than invisible. There is no delete
method, on purpose.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime

GENESIS = "0" * 64


def _canonical(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev_hash: str, entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256((prev_hash + _canonical(body)).encode()).hexdigest()


class ResearchLedger:
    """Append-only JSONL ledger with a hash chain."""

    def __init__(self, path: str = "data/research/ledger.jsonl"):
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    # -- writes -------------------------------------------------------------
    def append(self, cycle_id: str, kind: str, payload: dict | None = None) -> dict:
        """Append one entry and return it (with its hash)."""
        entries = self.entries()
        prev = entries[-1]["hash"] if entries else GENESIS
        entry = {
            "seq": len(entries),
            "at": datetime.now(UTC).isoformat(),
            "cycle": str(cycle_id),
            "kind": str(kind),
            "payload": dict(payload or {}),
            "prev": prev,
        }
        entry["hash"] = _digest(prev, entry)
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, sort_keys=True, default=str) + "\n")
        return entry

    def remove(self, *args, **kwargs):
        """Refused. A research record is permanent."""
        raise PermissionError("the research ledger is append-only; entries cannot be removed")

    # -- reads --------------------------------------------------------------
    def entries(self, cycle_id: str | None = None,
                kind: str | None = None) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        out: list[dict] = []
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if cycle_id is not None and entry.get("cycle") != cycle_id:
                    continue
                if kind is not None and entry.get("kind") != kind:
                    continue
                out.append(entry)
        return out

    def verify(self) -> dict:
        """Check the chain. Returns ``{"ok": bool, "broken_at": int|None}``."""
        prev = GENESIS
        entries = self.entries()
        for index, entry in enumerate(entries):
            if entry.get("prev") != prev:
                return {"ok": False, "broken_at": index, "reason": "previous hash mismatch"}
            if entry.get("hash") != _digest(prev, entry):
                return {"ok": False, "broken_at": index, "reason": "entry hash mismatch"}
            prev = entry["hash"]
        return {"ok": True, "broken_at": None, "entries": len(entries)}
