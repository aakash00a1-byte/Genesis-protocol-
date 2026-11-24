"""Provenance-aware memory (V7 investigation).

An append-only, hash-chained record of everything an investigation did: inputs,
evidence, hypotheses, decisions and outcomes. Two invariants matter more than
convenience:

* **History is never rewritten.** Entries are appended; there is no update or
  delete. Each entry commits to the hash of the previous one, so tampering with
  an earlier entry breaks the chain and ``verify_chain`` reports it.
* **Every entry carries its provenance.** Who/what produced it, from which
  source, at what time. An entry with no provenance is not stored.

This is deliberately small and dependency-free. It records; it does not reason.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List, Optional

GENESIS = "genesis"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(entry: Dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class Provenance:
    """Where a memory entry came from."""

    actor: str
    source: str = ""
    method: str = ""  # e.g. "web", "tool", "owner", "inference"
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.actor:
            raise ValueError("provenance requires an actor")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryEntry:
    seq: int
    kind: str
    payload: Dict[str, Any]
    provenance: Provenance
    ts: str = field(default_factory=utcnow)
    prev_hash: str = GENESIS
    hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["provenance"] = self.provenance.to_dict()
        return data


class ProvenanceMemory:
    """Append-only, hash-chained investigation memory.

    A JSONL file is the durable form; the same data is mirrored in memory for
    fast reads. ``path=None`` keeps it purely in memory (used in tests).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._lock = RLock()
        self._entries: List[MemoryEntry] = []
        if path and Path(path).exists():
            self._load()

    # -- write ---------------------------------------------------------------
    def append(self, kind: str, payload: Dict[str, Any], provenance: Provenance) -> MemoryEntry:
        if not kind:
            raise ValueError("memory entry requires a kind")
        with self._lock:
            prev = self._entries[-1].hash if self._entries else GENESIS
            entry = MemoryEntry(
                seq=len(self._entries),
                kind=kind,
                payload=dict(payload or {}),
                provenance=provenance,
                prev_hash=prev,
            )
            entry.hash = self._hash(entry)
            self._entries.append(entry)
            if self.path:
                self._persist(entry)
            return entry

    def _hash(self, entry: MemoryEntry) -> str:
        body = {
            "seq": entry.seq,
            "kind": entry.kind,
            "payload": entry.payload,
            "provenance": entry.provenance.to_dict(),
            "ts": entry.ts,
            "prev_hash": entry.prev_hash,
        }
        return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()

    def _persist(self, entry: MemoryEntry) -> None:
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry.to_dict(), sort_keys=True, default=str) + "\n"
        # Append with an exclusive lock so concurrent writers cannot interleave.
        with open(path, "a", encoding="utf-8") as fh:
            try:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except Exception:
                pass
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def _load(self) -> None:
        path = Path(self.path)
        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            prov = data.get("provenance") or {}
            entry = MemoryEntry(
                seq=data["seq"],
                kind=data["kind"],
                payload=data.get("payload") or {},
                provenance=Provenance(**prov),
                ts=data.get("ts", ""),
                prev_hash=data.get("prev_hash", GENESIS),
                hash=data.get("hash", ""),
            )
            self._entries.append(entry)

    # -- read ----------------------------------------------------------------
    def entries(self, kind: Optional[str] = None) -> List[MemoryEntry]:
        with self._lock:
            if kind is None:
                return list(self._entries)
            return [e for e in self._entries if e.kind == kind]

    def __len__(self) -> int:
        return len(self._entries)

    def verify_chain(self) -> Dict[str, Any]:
        """Recompute the chain. Returns ok=False at the first broken link."""
        with self._lock:
            prev = GENESIS
            for entry in self._entries:
                if entry.prev_hash != prev:
                    return {"ok": False, "broken_at": entry.seq, "reason": "prev_hash mismatch"}
                if entry.hash != self._hash(entry):
                    return {"ok": False, "broken_at": entry.seq, "reason": "hash mismatch"}
                prev = entry.hash
            return {"ok": True, "length": len(self._entries), "head": prev}

    def export(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.entries()]


__all__ = ["GENESIS", "Provenance", "MemoryEntry", "ProvenanceMemory"]
