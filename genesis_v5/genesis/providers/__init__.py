"""Genesis V5 Provider Fabric.

Provides the `Provider` protocol/ABC, the `ProviderFactory` registry, and a
built-in offline `MockProvider`. Real adapters (see `genesis.adapters`)
register here and remain disabled unless their configuration is complete.
"""
from __future__ import annotations

from .base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderStatus,
    ProviderHealth,
    FallbackPolicy,
)
from .factory import ProviderFactory
from .mock import MockProvider

__all__ = [
    "ModelCapability",
    "Provider",
    "ProviderCapabilities",
    "ProviderStatus",
    "ProviderHealth",
    "FallbackPolicy",
    "ProviderFactory",
    "MockProvider",
]