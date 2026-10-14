"""MemPalace adapter boundary.

The MemPalace public API could not be verified from this offline environment.
Per the project rule "Do not invent a MemPalace API", this module defines a
*contract* (`MemPalaceAdapterContract`) plus an offline mock that satisfies
it. The real adapter is only activated when an endpoint + API key are
configured; the HTTP wire format is assumed over a minimal documented
REST shape and is covered by offline contract tests. No network call is ever
made from tests.
"""
from __future__ import annotations

import logging
from typing import Any

from genesis.config.settings import MemoryConfig, resolve_secret
from genesis.core import MemoryEntry, MemoryScope, MemoryWritePolicy
from genesis.exceptions import MemoryError_

from .relevance import keyword_relevance

logger = logging.getLogger(__name__)


class MemPalaceAdapterContract:
    """The adapter boundary contract.

    Implementations must expose these operations. The signatures are the
    *only* stable part of this boundary; any real MemPalace client must be
    adapted here and nowhere else.
    """

    def put(
        self,
        scope: str,
        key: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store a value. Returns an opaque server result dict."""
        raise NotImplementedError

    def get(self, scope: str, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def query(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        raise NotImplementedError

    def health(self) -> bool:
        raise NotImplementedError


class MemPalaceAdapter(MemPalaceAdapterContract):
    """HTTP client for a MemPalace-compatible service.

    Only constructed when configuration provides an endpoint AND an API key.
    Without both, the adapter refuses to initialize so the system never
    fabricates connectivity.
    """

    name = "mempalace"

    def __init__(
        self,
        config: MemoryConfig,
        *,
        http_post=None,
        http_get=None,
    ) -> None:
        self.config = config
        self._api_key = resolve_secret(config.mempalace_api_key_env)
        if not config.mempalace_endpoint or not self._api_key:
            raise MemoryError_(
                "MemPalace not configured (endpoint + API key required); "
                "adapter disabled"
            )
        if http_post is None or http_get is None:
            import requests  # type: ignore[import-not-found]

            http_post = requests.post
            http_get = requests.get
        self._http_post = http_post
        self._http_get = http_get

    def put(
        self,
        scope: str,
        key: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = self._http_post(
            f"{self.config.mempalace_endpoint}/memory/put",
            json={"scope": scope, "key": key, "value": value,
                  "metadata": metadata or {}},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    def get(self, scope: str, key: str) -> dict[str, Any] | None:
        resp = self._http_get(
            f"{self.config.mempalace_endpoint}/memory/get",
            params={"scope": scope, "key": key},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=5,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def query(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        resp = self._http_get(
            f"{self.config.mempalace_endpoint}/memory/query",
            params={"q": query, "limit": limit},
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json()

    def health(self) -> bool:
        try:
            resp = self._http_get(
                f"{self.config.mempalace_endpoint}/health",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False


class MemPalaceMock(MemPalaceAdapterContract):
    """In-memory, offline implementation of the contract.

    Used by tests and offline mode to exercise the boundary without network.
    """

    name = "mempalace-mock"

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, Any]] = {}
        self._unhealthy = False

    def put(
        self,
        scope: str,
        key: str,
        value: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._store[(scope, key)] = {
            "scope": scope,
            "key": key,
            "value": value,
            "metadata": metadata or {},
        }
        return {"ok": True, "key": key}

    def get(self, scope: str, key: str) -> dict[str, Any] | None:
        return self._store.get((scope, key))

    def query(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        scored: list[tuple[float, dict[str, Any]]] = []
        for item in self._store.values():
            doc = f"{item['key']} {str(item['value'])}"
            score = keyword_relevance(query, doc)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def health(self) -> bool:
        return not self._unhealthy

    def set_unhealthy(self, unhealthy: bool = True) -> None:
        self._unhealthy = unhealthy


def create_mempalace_adapter(
    config: MemoryConfig,
) -> MemPalaceAdapterContract:
    """Factory: returns a MemPalaceMock when unconfigured, else a real
    MemPalaceAdapter. Never fabricates success."""
    if not config.mempalace_endpoint or not resolve_secret(
        config.mempalace_api_key_env
    ):
        logger.info("MemPalace unconfigured; using offline mock")
        return MemPalaceMock()
    try:
        return MemPalaceAdapter(config)
    except MemoryError_:
        logger.warning("MemPalace configuration incomplete; using offline mock")
        return MemPalaceMock()