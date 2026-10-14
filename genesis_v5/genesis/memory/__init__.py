"""Genesis V5 Memory Fabric.

Scoped, policy-controlled memory with relevance filtering, secret
sanitization, duplicate/conflict handling, and graceful failure.
"""
from __future__ import annotations

from .provider import MemoryProvider, Memory
from .adapter import ProviderMemoryAdapter
from .mempalace import (
    MemPalaceAdapter,
    MemPalaceAdapterContract,
    create_mempalace_adapter,
)
from .relevance import keyword_relevance

__all__ = [
    "MemoryProvider",
    "Memory",
    "ProviderMemoryAdapter",
    "MemPalaceAdapter",
    "MemPalaceAdapterContract",
    "create_mempalace_adapter",
    "keyword_relevance",
]