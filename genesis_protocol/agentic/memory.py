"""Durable, user-isolated memory for GLUTEN.

The existing ``genesis_protocol.memory.UnifiedMemory`` keeps its long-term
store in a ChromaDB *in-memory* client and falls back to a hash-based
embedding, so nothing survives a restart. This module is a small, explicit
SQLite store that actually persists to disk and enforces user isolation at the
query level.

Contract:

* Only approved facts are stored; a caller must pass ``approved=True``.
* Credential-shaped content is refused, never written.
* Instruction-shaped content is refused: stored text is untrusted data and is
  never treated as an executable instruction (see ``agentic/memory_safety``).
* Every read/write is scoped by ``user_id``; one user can never see another's
  memory.
* Memories can be inspected, corrected and deleted by their owner.
* Recall spans sessions: a new session for the same user sees earlier facts.

V7 P3 adds provenance, verification status, confidence and freshness so a
memory can be told apart as a *verified fact*, *user-provided* information, a
*hypothesis* or an *unverified claim*. Only an owner may promote an item to
``verified``; an agent can never promote its own assumption into a fact.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.memory_safety import (
    UnsafeMemory,
    is_instruction_like,
    looks_like_secret,
    redact_secrets,
    scan_content,
)

__all__ = [
    "AgentMemory",
    "MemoryRejected",
    "get_agent_memory",
    "looks_like_secret",
    "is_instruction_like",
    "VERIFICATION_LEVELS",
    "MEMORY_SOURCES",
]

MAX_CONTENT_LEN = 4000

# Ordered from least to most trustworthy. ``verified`` is the only level an
# agent cannot set for itself.
VERIFICATION_LEVELS = ("unverified", "hypothesis", "user_provided", "verified")

# Where a memory came from. Provenance is descriptive, not a trust grant.
MEMORY_SOURCES = ("user", "owner", "agent", "task", "reflection", "import")


class MemoryRejected(UnsafeMemory):
    """Raised when content must not be stored (secret/instruction-shaped or too long).

    Subclasses :class:`UnsafeMemory` so callers that already catch
    ``MemoryRejected`` keep working and callers of the safety layer catch the
    same error.
    """


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


class AgentMemory:
    """SQLite-backed durable memory with strict per-user isolation."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(Path("data") / "gluten_memory.db")
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # check_same_thread=False so the store works across the threads the
        # Flask app and tests use; the lock serialises writes.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # -- schema ---------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id            TEXT PRIMARY KEY,
                    user_id       INTEGER NOT NULL,
                    session_id    TEXT,
                    kind          TEXT NOT NULL DEFAULT 'fact',
                    content       TEXT NOT NULL,
                    source        TEXT NOT NULL DEFAULT 'user',
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_mem_user ON agent_memories(user_id)"
            )
        # Additive columns. Existing databases predate P3, so each column is
        # added only if missing; this is the whole migration.
        for column, ddl in (
            ("verification", "TEXT NOT NULL DEFAULT 'unverified'"),
            ("confidence", "REAL NOT NULL DEFAULT 0.5"),
            ("origin", "TEXT"),
            ("provenance", "TEXT"),
            ("expires_at", "TEXT"),
            ("superseded_by", "TEXT"),
            ("deleted", "INTEGER NOT NULL DEFAULT 0"),
            ("deleted_at", "TEXT"),
            ("updated_by", "INTEGER"),
        ):
            self._ensure_column(column, ddl)

    def _ensure_column(self, column: str, ddl: str) -> None:
        with self._lock, self._conn:
            existing = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(agent_memories)").fetchall()
            }
            if column not in existing:
                self._conn.execute(f"ALTER TABLE agent_memories ADD COLUMN {column} {ddl}")

    # -- validation -----------------------------------------------------------

    @staticmethod
    def _validate(content: str) -> str:
        content = (content or "").strip()
        if len(content) > MAX_CONTENT_LEN:
            raise MemoryRejected(f"content exceeds {MAX_CONTENT_LEN} characters")
        ok, reason = scan_content(content)
        if not ok:
            raise MemoryRejected(reason)
        return content

    # -- writes ---------------------------------------------------------------

    def remember(
        self,
        user_id: int,
        content: str,
        kind: str = "fact",
        session_id: Optional[str] = None,
        approved: bool = False,
        source: str = "user",
        verification: str = "unverified",
        confidence: float = 0.5,
        origin: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        expires_at: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> str:
        """Store an approved memory. Raises ``MemoryRejected`` otherwise.

        ``approved`` must be True: memory is opt-in, never scraped silently.
        ``verification`` may be any level except ``verified``: only the owner can
        verify a memory through :meth:`verify`. An agent cannot certify its own
        assumption as fact.
        """
        if not approved:
            raise MemoryRejected("memory is only stored when approved=True")
        content = self._validate(content)
        if verification not in VERIFICATION_LEVELS:
            raise MemoryRejected(f"unknown verification level '{verification}'")
        if verification == "verified":
            raise MemoryRejected(
                "only the owner may store a memory as verified; use verify() with owner approval"
            )
        if source not in MEMORY_SOURCES:
            raise MemoryRejected(f"unknown source '{source}'")

        memory_id = uuid.uuid4().hex[:12]
        now = _utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_memories (id, user_id, session_id, kind, content, source,"
                " created_at, updated_at, verification, confidence, origin, provenance,"
                " expires_at, superseded_by, deleted, deleted_at, updated_by)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
                (
                    memory_id, int(user_id), session_id, kind, content, source,
                    now, now, verification, _coerce_confidence(confidence),
                    origin, json.dumps(provenance) if provenance else None,
                    expires_at, None, int(user_id),
                ),
            )
            if supersedes:
                self._conn.execute(
                    "UPDATE agent_memories SET superseded_by = ?, updated_at = ?"
                    " WHERE id = ? AND user_id = ?",
                    (memory_id, now, supersedes, int(user_id)),
                )
        return memory_id

    def correct(
        self, user_id: int, memory_id: str, new_content: str, updated_by: Optional[int] = None
    ) -> bool:
        """Replace a memory's content. Only the owner may correct it.

        Correcting content invalidates any prior verification: a changed fact is
        no longer the thing that was verified, so it drops back to
        ``user_provided``. This stops content being swapped under a ``verified``
        badge.
        """
        new_content = self._validate(new_content)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE agent_memories SET content = ?, updated_at = ?,"
                " verification = CASE WHEN verification = 'verified' THEN 'user_provided'"
                " ELSE verification END, updated_by = ?"
                " WHERE id = ? AND user_id = ? AND deleted = 0",
                (new_content, _utcnow(), updated_by if updated_by is not None else int(user_id),
                 memory_id, int(user_id)),
            )
            return cur.rowcount > 0

    def verify(
        self, user_id: int, memory_id: str, owner_approved: bool = False,
        confidence: float = 1.0, note: str = "",
    ) -> bool:
        """Promote a memory to ``verified``. Owner-only.

        This is the only path to ``verified``. It requires explicit owner
        approval, so an assumption cannot become a verified fact on its own.
        """
        if not owner_approved:
            raise MemoryRejected("promoting a memory to verified requires owner approval")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE agent_memories SET verification = 'verified', confidence = ?,"
                " updated_at = ?, updated_by = ?, provenance = ?"
                " WHERE id = ? AND user_id = ? AND deleted = 0",
                (
                    _coerce_confidence(confidence, 1.0), _utcnow(), int(user_id),
                    json.dumps({"verified_note": redact_secrets(note)[:200]}) if note else None,
                    memory_id, int(user_id),
                ),
            )
            return cur.rowcount > 0

    def revoke(self, user_id: int, memory_id: str, reason: str = "") -> bool:
        """Soft-delete a memory (revocation). The row is retained for the audit trail.

        Revoked memories are excluded from every read, so recall never returns
        them, but the fact that a deletion happened is not erased.
        """
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE agent_memories SET deleted = 1, deleted_at = ?, updated_at = ?,"
                " provenance = ?, updated_by = ?"
                " WHERE id = ? AND user_id = ? AND deleted = 0",
                (
                    _utcnow(), _utcnow(),
                    json.dumps({"revoked_reason": redact_secrets(reason)[:200]}) if reason else None,
                    int(user_id), memory_id, int(user_id),
                ),
            )
            return cur.rowcount > 0

    def forget(self, user_id: int, memory_id: str) -> bool:
        """Delete a memory. Only the owner may delete it.

        This is the historical entry point; it now performs a revocation
        (soft delete) so the deletion itself is auditable. Use
        :meth:`hard_delete` to purge the row entirely.
        """
        return self.revoke(user_id, memory_id, reason="forget")

    def hard_delete(self, user_id: int, memory_id: str) -> bool:
        """Permanently purge a revoked memory's row. Owner-scoped."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM agent_memories WHERE id = ? AND user_id = ? AND deleted = 1",
                (memory_id, int(user_id)),
            )
            return cur.rowcount > 0

    # -- reads ----------------------------------------------------------------

    def get(self, user_id: int, memory_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one memory by id, scoped to its owner."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, int(user_id)),
            ).fetchone()
        return dict(row) if row else None

    def list_memories(
        self, user_id: int, kind: Optional[str] = None, include_revoked: bool = False
    ) -> List[Dict[str, Any]]:
        """Inspect a user's memories, newest first. Revoked items are hidden."""
        sql = "SELECT * FROM agent_memories WHERE user_id = ?"
        params: List[Any] = [int(user_id)]
        if not include_revoked:
            sql += " AND deleted = 0"
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def recall(
        self, user_id: int, query: str = "", limit: int = 10, include_expired: bool = False
    ) -> List[Dict[str, Any]]:
        """Return memories relevant to ``query`` for this user only.

        Relevance is keyword overlap, then recency. Recall is cross-session by
        design: memories from earlier sessions of the same user are eligible.
        Revoked memories are never returned. Each item carries its provenance,
        verification status, confidence and freshness so the caller can judge it.
        """
        limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agent_memories WHERE user_id = ? AND deleted = 0"
                " ORDER BY created_at DESC",
                (int(user_id),),
            ).fetchall()
        memories = [dict(r) for r in rows]
        if not include_expired:
            memories = [m for m in memories if not self._is_expired(m)]
        terms = {t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 2}
        if not terms:
            return memories[:limit]

        def score(mem: Dict[str, Any]) -> int:
            text = mem["content"].lower()
            return sum(1 for t in terms if t in text)

        scored = [(score(m), m) for m in memories]
        relevant = [m for s, m in scored if s > 0]
        relevant.sort(key=lambda m: m["created_at"], reverse=True)
        if not relevant:
            return memories[:limit]
        return relevant[:limit]

    @staticmethod
    def _is_expired(memory: Dict[str, Any]) -> bool:
        expires_at = memory.get("expires_at")
        if not expires_at:
            return False
        try:
            return datetime.fromisoformat(expires_at) < datetime.now(timezone.utc)
        except (TypeError, ValueError):
            return False

    def count(self, user_id: int) -> int:
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM agent_memories WHERE user_id = ? AND deleted = 0",
                    (int(user_id),),
                ).fetchone()[0]
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


_default: Optional[AgentMemory] = None


def get_agent_memory(db_path: Optional[str] = None) -> AgentMemory:
    """Return a process-wide memory store (path from GLUTEN_MEMORY_DB if set)."""
    global _default
    if db_path is None:
        import os

        db_path = os.environ.get("GLUTEN_MEMORY_DB") or str(Path("data") / "gluten_memory.db")
    if _default is None or _default.db_path != db_path:
        _default = AgentMemory(db_path)
    return _default
