"""ProviderMemoryAdapter: bridge the MemoryProvider to external stores.

This is a clean boundary for swapping the in-process store for an external
memory backend. The current implementation only supports the local provider;
an external backend must implement `MemoryBackend` and be wired through the
factory. If the backend cannot be reached, reads/writes report failure
gracefully without fabricating success.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from genesis.config.settings import MemoryConfig
from genesis.core import MemoryEntry, MemoryScope, MemoryWritePolicy, now_ms
from genesis.exceptions import MemoryError_

from .relevance import keyword_relevance

logger = logging.getLogger(__name__)


class MemoryBackend(Protocol):
    """Contract any external memory backend must satisfy."""

    def write(self, entry: MemoryEntry) -> None: ...

    def read(self, scope: MemoryScope, key: str) -> MemoryEntry | None: ...

    def search(
        self, query: str, scopes: list[MemoryScope], top_k: int
    ) -> list[MemoryEntry]: ...

    def health(self) -> bool: ...


class ProviderMemoryAdapter:
    """Present a MemoryBackend through the same API as MemoryProvider.

    Used when a backend other than the local store is configured. Unreachable
    backends produce a MemoryError_ (graceful failure by default).
    """

    name = "adapter"

    def __init__(
        self,
        backend: MemoryBackend,
        config: MemoryConfig | None = None,
    ) -> None:
        self._backend = backend
        self.config = config or MemoryConfig()

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
        if not self._backend.health():
            raise MemoryError_("memory backend unreachable")
        entry = MemoryEntry(
            scope=scope,
            key=key,
            value=value,
            metadata=dict(metadata or {}),
        )
        self._backend.write(entry)
        return entry

    def read(self, scope: MemoryScope, key: str, **kwargs: Any) -> MemoryEntry | None:
        if not self._backend.health():
            raise MemoryError_("memory backend unreachable")
        return self._backend.read(scope, key)

    def search(
        self, query: str, **kwargs: Any
    ) -> list[MemoryEntry]:
        scopes = kwargs.get("scopes") or [s for s in MemoryScope]
        top_k = kwargs.get("top_k") or self.config.relevance_top_k
        if not self._backend.health():
            raise MemoryError_("memory backend unreachable")
        return self._backend.search(query, scopes, top_k)

    def health(self) -> bool:
        try:
            return self._backend.health()
        except Exception:  # noqa: BLE001
            return False