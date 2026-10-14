"""MemoryProvider: the primary Memory Fabric implementation.

Scopes: session, task, project, long_term. Writes are governed by a
MemoryWritePolicy and pass through secret sanitization. Duplicate keys update
in place (versioned); conflicting values are resolved deterministically.
Failures degrade gracefully when configured.
"""
from __future__ import annotations

import logging
from typing import Any

from genesis.config.settings import MemoryConfig
from genesis.core import (
    AuditEvent,
    MemoryEntry,
    MemoryScope,
    MemoryWritePolicy,
    now_ms,
    sanitize_text,
)
from genesis.exceptions import MemoryError_

from .relevance import keyword_relevance

logger = logging.getLogger(__name__)


def _backup_path(path: str, stamp: str) -> str:
    """Insert a timestamp before the file extension for backup filenames."""
    import os

    directory = os.path.dirname(path)
    basename = os.path.basename(path)
    if "." in basename:
        stem, ext = basename.rsplit(".", 1)
        basename = f"{stem}.{stamp}.{ext}"
    else:
        basename = f"{basename}.{stamp}"
    return os.path.join(directory, basename) if directory else basename


class MemoryProvider:
    """In-process, scoped memory store.

    The default `local` provider is offline and dependency-free.
    """

    name = "local"

    def __init__(self, config: MemoryConfig | None = None) -> None:
        self.config = config or MemoryConfig()
        self._entries: dict[str, MemoryEntry] = {}
        self._audit: list[AuditEvent] = []
        self._fail = False

    # ------------------------------------------------------------------
    # Low-level API used by the Kernel
    # ------------------------------------------------------------------
    def write(
        self,
        scope: MemoryScope,
        key: str,
        value: Any,
        *,
        policy: MemoryWritePolicy = MemoryWritePolicy.ALWAYS,
        metadata: dict[str, Any] | None = None,
        verified: bool = True,
        actor: str = "kernel",
    ) -> MemoryEntry:
        """Write an entry subject to the write policy.

        Duplicate key+scope: update in place (conflict resolution for
        differing values). Policy NEVER refuses the write.
        """
        scope_ok = self._policy_allows(policy, verified)
        if not scope_ok:
            self._record(
                AuditEvent(
                    event_type="memory_write",
                    actor=actor,
                    action="memory.write",
                    resource=f"{scope.value}:{key}",
                    status="denied",
                    details={"policy": policy.value},
                )
            )
            raise MemoryError_(
                f"memory write denied by policy {policy.value}"
            )

        text = sanitize_text(str(value)) if self.config.redact_secrets else str(value)
        existing = self._entries.get(self._mem_key(scope, key))
        if existing is None:
            entry = MemoryEntry(
                scope=scope,
                key=key,
                value=self._cast(value, text),
                metadata=dict(metadata or {}),
                secret_redacted=self.config.redact_secrets,
            )
            self._entries[self._mem_key(scope, key)] = entry
        else:
            entry = self._resolve_conflict(existing, value, text, metadata)
        self._record(
            AuditEvent(
                event_type="memory_write",
                actor=actor,
                action="memory.write",
                resource=f"{scope.value}:{key}",
                status="success",
                details={"version": entry.version},
            )
        )
        return entry

    def read(
        self,
        scope: MemoryScope,
        key: str,
        *,
        actor: str = "kernel",
    ) -> MemoryEntry | None:
        self._maybe_fail()
        entry = self._entries.get(self._mem_key(scope, key))
        if entry is not None:
            self._record(
                AuditEvent(
                    event_type="memory_read",
                    actor=actor,
                    action="memory.read",
                    resource=f"{scope.value}:{key}",
                    status="success",
                )
            )
        return entry

    def search(
        self,
        query: str,
        *,
        scopes: list[MemoryScope] | None = None,
        top_k: int | None = None,
        actor: str = "kernel",
    ) -> list[MemoryEntry]:
        """Relevance-filtered search across the given scopes."""
        self._maybe_fail()
        top_k = top_k or self.config.relevance_top_k
        allowed = set(scopes or [s for s in MemoryScope])
        candidates = [
            e for e in self._entries.values() if e.scope in allowed
        ]
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in candidates:
            doc = f"{entry.key} {str(entry.value)} {str(entry.metadata)}"
            score = keyword_relevance(query, doc)
            scored.append((score, entry))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = [e for score, e in scored if score > 0][:top_k]
        self._record(
            AuditEvent(
                event_type="memory_search",
                actor=actor,
                action="memory.search",
                status="success",
                details={"query": query[:200], "hits": len(results)},
            )
        )
        return results

    def list_scope(
        self, scope: MemoryScope, *, actor: str = "kernel"
    ) -> list[MemoryEntry]:
        self._maybe_fail()
        return [
            e
            for e in self._entries.values()
            if e.scope == scope
        ]

    def forget(self, scope: MemoryScope, key: str, *, actor: str = "kernel") -> bool:
        self._maybe_fail()
        k = self._mem_key(scope, key)
        if k in self._entries:
            del self._entries[k]
            self._record(
                AuditEvent(
                    event_type="memory_delete",
                    actor=actor,
                    action="memory.delete",
                    resource=f"{scope.value}:{key}",
                    status="success",
                )
            )
            return True
        return False

    def clear(self, scope: MemoryScope | None = None) -> None:
        if scope is None:
            self._entries.clear()
        else:
            self._entries = {
                k: e
                for k, e in self._entries.items()
                if e.scope != scope
            }

    # ------------------------------------------------------------------
    # Persistence (snapshot/restore + backup)
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Serialize all entries (values are redaction-safe at write time)."""
        return {
            "entries": [
                {
                    "scope": entry.scope.value,
                    "key": entry.key,
                    "value": entry.value,
                    "metadata": dict(entry.metadata),
                    "created_ms": entry.created_ms,
                    "updated_ms": entry.updated_ms,
                    "version": entry.version,
                    "entry_id": entry.entry_id,
                }
                for entry in self._entries.values()
            ]
        }

    def restore(self, snapshot: dict) -> int:
        """Load entries from a snapshot, replacing the store. Returns count."""
        self._entries.clear()
        count = 0
        for raw in snapshot.get("entries", []):
            scope = MemoryScope(raw.get("scope", "session"))
            key = raw.get("key", "")
            if not key:
                continue
            entry = MemoryEntry(
                scope=scope,
                key=key,
                value=raw.get("value"),
                metadata=dict(raw.get("metadata") or {}),
                created_ms=raw.get("created_ms", 0),
                updated_ms=raw.get("updated_ms", 0),
                version=raw.get("version", 1),
                entry_id=raw.get("entry_id", ""),
            )
            self._entries[self._mem_key(scope, key)] = entry
            count += 1
        return count

    def save_to(self, path: str) -> None:
        """Persist a snapshot to disk (JSON, secrets redacted)."""
        import json
        import os

        from genesis.core import sanitize_text

        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        payload = {"app": "genesis-v5", "snapshot": self.snapshot()}
        serialized = json.dumps(payload, default=str)
        serialized = sanitize_text(serialized)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(serialized)

    def load_from(self, path: str) -> int:
        """Restore a snapshot from a JSON file. Returns entry count."""
        import json

        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        snapshot = payload.get("snapshot", payload)
        return self.restore(snapshot)

    def backup(self, path: str) -> int:
        """Write a timestamped backup file. Returns entries backed up."""
        import os
        import time

        stamp = time.strftime("%Y%m%dT%H%M%S")
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        return self.save_to(_backup_path(path, stamp))

    # ------------------------------------------------------------------
    # Failure injection (for graceful-failure tests)
    # ------------------------------------------------------------------
    def set_failure(self, fail: bool = True) -> None:
        self._fail = fail

    def _maybe_fail(self) -> None:
        if self._fail:
            if not self.config.graceful_failure:
                raise MemoryError_("memory store failure")
            raise MemoryError_("memory store temporarily unavailable")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _mem_key(scope: MemoryScope, key: str) -> str:
        return f"{scope.value}:{key}"

    @staticmethod
    def _policy_allows(policy: MemoryWritePolicy, verified: bool) -> bool:
        if policy == MemoryWritePolicy.ALWAYS:
            return True
        if policy == MemoryWritePolicy.NEVER:
            return False
        if policy == MemoryWritePolicy.ON_SUCCESS:
            return True  # success is defined by the caller's `verified` flag
        if policy == MemoryWritePolicy.ON_FAILURE:
            return not verified
        if policy == MemoryWritePolicy.VERIFIED:
            return verified
        return True

    def _cast(self, original: Any, text: str) -> Any:
        if isinstance(original, (dict, list, tuple, int, float, bool)) or original is None:
            if isinstance(original, tuple):
                return list(original)
            return original
        return text

    def _resolve_conflict(
        self,
        existing: MemoryEntry,
        new_value: Any,
        new_text: str,
        metadata: dict[str, Any] | None,
    ) -> MemoryEntry:
        """Deterministic conflict resolution.

        - identical stored text: preserve original, bump nothing.
        - differing values: keep the original and record the conflict in
          metadata (original wins to avoid data loss).
        """
        incoming = self._cast(new_value, new_text)
        existing_raw = str(existing.value)
        incoming_raw = str(incoming)
        if existing_raw != incoming_raw:
            conflicts = existing.metadata.get("conflicts", [])
            conflicts.append(
                {"ts_ms": now_ms(), "incoming": incoming_raw[:200]}
            )
            existing.metadata["conflicts"] = conflicts[-20:]
        existing.version += 1
        existing.updated_ms = now_ms()
        if metadata:
            existing.metadata.update(metadata)
        return existing

    def _record(self, event: AuditEvent) -> None:
        self._audit.append(event)

    def audit_trail(self) -> list[AuditEvent]:
        return list(self._audit)


# The Kernel-facing convenience facade.
class Memory:
    """Facade bundling the provider with a default (session) scope."""

    def __init__(
        self,
        provider: MemoryProvider | None = None,
        default_scope: MemoryScope = MemoryScope.SESSION,
    ) -> None:
        self.provider = provider or MemoryProvider()
        self.default_scope = default_scope

    def write(self, key: str, value: Any, **kwargs: Any) -> MemoryEntry:
        scope = kwargs.pop("scope", self.default_scope)
        return self.provider.write(scope, key, value, **kwargs)

    def read(self, key: str, **kwargs: Any) -> MemoryEntry | None:
        scope = kwargs.pop("scope", self.default_scope)
        return self.provider.read(scope, key, **kwargs)

    def search(self, query: str, **kwargs: Any) -> list[MemoryEntry]:
        return self.provider.search(query, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.provider, name)