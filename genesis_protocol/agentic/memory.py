"""Durable, user-isolated memory for GLUTEN.

The existing ``genesis_protocol.memory.UnifiedMemory`` keeps its long-term
store in a ChromaDB *in-memory* client and falls back to a hash-based
embedding, so nothing survives a restart. This module is a small, explicit
SQLite store that actually persists to disk and enforces user isolation at the
query level.

Contract:

* Only approved facts are stored; a caller must pass ``approved=True``.
* Credential-shaped content is refused, never written.
* Every read/write is scoped by ``user_id``; one user can never see another's
  memory.
* Memories can be inspected, corrected and deleted by their owner.
* Recall spans sessions: a new session for the same user sees earlier facts.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Credential-shaped content is refused rather than stored. These patterns are
# deliberately broad: a false positive only means the user rephrases, while a
# false negative would persist a secret.
_SECRET_PATTERNS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{16,}\b"),                 # OpenAI-style keys
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b"),                        # Groq
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"),                     # Google API key
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),                # Slack
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),                  # GitHub token
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                            # AWS access key id
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),              # PEM private key
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),  # JWT
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S{4,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
]

MAX_CONTENT_LEN = 4000


def looks_like_secret(text: str) -> bool:
    """True when ``text`` contains something shaped like a credential."""
    return any(p.search(text or "") for p in _SECRET_PATTERNS)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryRejected(ValueError):
    """Raised when content must not be stored (secret-shaped or too long)."""


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

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_memories (
                    id          TEXT PRIMARY KEY,
                    user_id     INTEGER NOT NULL,
                    session_id  TEXT,
                    kind        TEXT NOT NULL DEFAULT 'fact',
                    content     TEXT NOT NULL,
                    source      TEXT NOT NULL DEFAULT 'user',
                    created_at  TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_mem_user ON agent_memories(user_id)"
            )

    # -- writes ---------------------------------------------------------------

    def remember(
        self,
        user_id: int,
        content: str,
        kind: str = "fact",
        session_id: Optional[str] = None,
        approved: bool = False,
    ) -> str:
        """Store an approved fact. Raises ``MemoryRejected`` otherwise.

        ``approved`` must be True: memory is opt-in, never scraped silently.
        """
        if not approved:
            raise MemoryRejected("memory is only stored when approved=True")
        content = (content or "").strip()
        if not content:
            raise MemoryRejected("empty content")
        if len(content) > MAX_CONTENT_LEN:
            raise MemoryRejected(f"content exceeds {MAX_CONTENT_LEN} characters")
        if looks_like_secret(content):
            raise MemoryRejected("content looks like a credential; refused")

        memory_id = uuid.uuid4().hex[:12]
        now = _utcnow()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO agent_memories (id, user_id, session_id, kind, content, source, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (memory_id, int(user_id), session_id, kind, content, "user", now, now),
            )
        return memory_id

    def correct(self, user_id: int, memory_id: str, new_content: str) -> bool:
        """Replace a memory's content. Only the owner may correct it."""
        new_content = (new_content or "").strip()
        if not new_content:
            raise MemoryRejected("empty content")
        if len(new_content) > MAX_CONTENT_LEN:
            raise MemoryRejected(f"content exceeds {MAX_CONTENT_LEN} characters")
        if looks_like_secret(new_content):
            raise MemoryRejected("content looks like a credential; refused")
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE agent_memories SET content = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (new_content, _utcnow(), memory_id, int(user_id)),
            )
            return cur.rowcount > 0

    def forget(self, user_id: int, memory_id: str) -> bool:
        """Delete a memory. Only the owner may delete it."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM agent_memories WHERE id = ? AND user_id = ?",
                (memory_id, int(user_id)),
            )
            return cur.rowcount > 0

    # -- reads ----------------------------------------------------------------

    def list_memories(self, user_id: int, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        """Inspect a user's memories, newest first."""
        sql = "SELECT * FROM agent_memories WHERE user_id = ?"
        params: List[Any] = [int(user_id)]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def recall(self, user_id: int, query: str = "", limit: int = 10) -> List[Dict[str, Any]]:
        """Return memories relevant to ``query`` for this user only.

        Relevance is keyword overlap, then recency. Recall is cross-session by
        design: memories from earlier sessions of the same user are eligible.
        """
        limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM agent_memories WHERE user_id = ? ORDER BY created_at DESC",
                (int(user_id),),
            ).fetchall()
        memories = [dict(r) for r in rows]
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

    def count(self, user_id: int) -> int:
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) FROM agent_memories WHERE user_id = ?", (int(user_id),)
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
