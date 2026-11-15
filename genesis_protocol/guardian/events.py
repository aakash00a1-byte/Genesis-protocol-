"""Tamper-evident security event log for the AI Guardian (V7 P5).

The existing ``agentic.audit.AuditLog`` records agent tool decisions in JSONL and
redacts secrets, but it is not tamper-evident: a line can be edited or removed
without detection. Forensics needs the opposite property, so this is a small,
separate hash-chained log.

Each entry stores the SHA-256 of ``previous_hash + canonical(entry)``. Editing,
reordering or deleting any entry breaks the chain from that point on, which
``verify()`` reports with the first broken index. This does not prevent an
attacker with write access from rewriting the whole chain, but it makes a
targeted edit detectable, which is what an evidence trail needs.

Contract:

* Append-only. Entries are written once and never updated.
* Every entry carries a UTC timestamp, a sequence number and the chain hash.
* Payloads are redacted before they are stored, so no secret is ever persisted.
* ``verify()`` returns the first index whose hash does not match, or -1 if the
  chain is intact.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.audit import _redact

# Event categories the guardian emits. Kept small and explicit so a reader can
# reason about the whole set.
CATEGORIES = (
    "threat_intel",
    "auth",
    "webhook",
    "api",
    "identity",
    "privilege",
    "secret",
    "tool",
    "behaviour",
    "health",
    "integrity",
    "response",
    "anomaly",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(entry: Dict[str, Any]) -> str:
    """Deterministic serialisation of an entry for hashing."""
    return json.dumps(entry, sort_keys=True, separators=(",", ":"), default=str)


def _chain_hash(previous_hash: str, entry: Dict[str, Any]) -> str:
    return hashlib.sha256((previous_hash + _canonical(entry)).encode("utf-8")).hexdigest()


@dataclass
class SecurityEvent:
    """One recorded security event."""

    seq: int
    ts: str
    category: str
    event: str
    severity: str  # info | low | medium | high | critical
    actor: Optional[str] = None
    subject: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    source: str = "guardian"
    prev_hash: str = ""
    hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SecurityEventLog:
    """Append-only, hash-chained security event log."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get("GLUTEN_SECURITY_LOG") or str(Path("data") / "gluten_security.jsonl")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory: List[Dict[str, Any]] = []

    # -- writes ---------------------------------------------------------------

    def record(
        self,
        category: str,
        event: str,
        severity: str = "info",
        actor: Optional[str] = None,
        subject: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        source: str = "guardian",
    ) -> SecurityEvent:
        """Append one event. ``evidence`` is redacted before storage."""
        if category not in CATEGORIES:
            raise ValueError(f"unknown security category '{category}'")
        safe_evidence = json.loads(_redact(json.dumps(evidence or {}, default=str), limit=4000))
        with self._lock:
            entries = self._read_all_unlocked()
            previous_hash = entries[-1]["hash"] if entries else "genesis"
            seq = (entries[-1]["seq"] + 1) if entries else 0
            body = {
                "seq": seq,
                "ts": _utcnow(),
                "category": category,
                "event": event,
                "severity": severity,
                "actor": actor,
                "subject": subject,
                "evidence": safe_evidence,
                "source": source,
                "prev_hash": previous_hash,
            }
            body["hash"] = _chain_hash(previous_hash, body)
            if self.path == ":memory:":
                self._memory.append(body)
            else:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(body, default=str) + "\n")
        return SecurityEvent(**body)

    # -- reads ----------------------------------------------------------------

    def _read_all_unlocked(self) -> List[Dict[str, Any]]:
        if self.path == ":memory:":
            return list(self._memory)
        if not Path(self.path).exists():
            return []
        out = []
        for line in Path(self.path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return recorded entries, oldest first (optionally only the last ``limit``)."""
        with self._lock:
            rows = self._read_all_unlocked()
        return rows[-limit:] if limit else rows

    def verify(self) -> Dict[str, Any]:
        """Recompute the chain. Returns ``{"ok": bool, "broken_at": int, ...}``."""
        with self._lock:
            rows = self._read_all_unlocked()
        previous_hash = "genesis"
        for index, row in enumerate(rows):
            expected = _chain_hash(previous_hash, {k: v for k, v in row.items() if k != "hash"})
            if row.get("hash") != expected or row.get("prev_hash") != previous_hash:
                return {"ok": False, "broken_at": index, "total": len(rows)}
            previous_hash = row["hash"]
        return {"ok": True, "broken_at": -1, "total": len(rows)}

    def incident_timeline(
        self, actor: Optional[str] = None, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """A time-ordered view of events, filtered by actor and/or category."""
        rows = self.entries()
        if actor is not None:
            rows = [r for r in rows if r.get("actor") == actor]
        if category is not None:
            rows = [r for r in rows if r.get("category") == category]
        return sorted(rows, key=lambda r: r.get("ts", ""))

    def count(self, category: Optional[str] = None) -> int:
        rows = self.entries()
        if category:
            rows = [r for r in rows if r.get("category") == category]
        return len(rows)


_default: Optional[SecurityEventLog] = None


def get_security_log(path: Optional[str] = None) -> SecurityEventLog:
    """Process-wide security event log (path from GLUTEN_SECURITY_LOG if set)."""
    global _default
    if path is None:
        path = os.environ.get("GLUTEN_SECURITY_LOG") or str(Path("data") / "gluten_security.jsonl")
    if _default is None or _default.path != path:
        _default = SecurityEventLog(path)
    return _default
