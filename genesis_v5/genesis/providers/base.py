"""Provider abstraction for Genesis V5.

Every provider adapter implements `Provider`. Normalized responses and errors
are produced at this boundary so the Kernel and Router never depend on
provider-specific formats.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.core import ModelResult
from genesis.exceptions import ProviderError


class ModelCapability(str, Enum):
    """Capabilities a model may advertise for router capability analysis."""

    CHAT = "chat"
    CODE = "code"
    REASONING = "reasoning"
    AGENTIC = "agentic"
    PLANNING = "planning"
    RESEARCH = "research"
    QA = "qa"
    IMAGE_INPUT = "image_input"
    LONG_CONTEXT = "long_context"
    FUNCTION_CALLING = "function_calling"


class ProviderStatus(str, Enum):
    READY = "ready"
    DISABLED = "disabled"
    ERROR = "error"
    DEGRADED = "degraded"


@dataclass
class ProviderHealth:
    provider: str
    status: ProviderStatus
    ok: bool
    latency_ms: int = 0
    message: str = ""
    checked_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "status": self.status.value,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "checked_ms": self.checked_ms,
        }


@dataclass
class ProviderCapabilities:
    provider: str
    models: list[str] = field(default_factory=list)
    capabilities: list[ModelCapability] = field(default_factory=list)
    max_context_tokens: int = 4096
    cost_per_1k_tokens: float = 0.0
    reliability: float = 1.0  # 0..1
    supports_streaming: bool = False
    needs_credentials: bool = False
    offline: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "models": list(self.models),
            "capabilities": [c.value for c in self.capabilities],
            "max_context_tokens": self.max_context_tokens,
            "cost_per_1k_tokens": self.cost_per_1k_tokens,
            "reliability": self.reliability,
            "supports_streaming": self.supports_streaming,
            "needs_credentials": self.needs_credentials,
            "offline": self.offline,
        }


@dataclass
class FallbackPolicy:
    """Controls bounded fallback. Disable to prevent infinite loops."""

    enabled: bool = True
    max_depth: int = 3
    on_rate_limit: bool = True
    on_timeout: bool = True
    on_http_error: bool = True


class Provider(ABC):
    """Interface every provider adapter implements."""

    name: str = "base"
    offline: bool = False
    needs_credentials: bool = False

    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Return the provider health. Never raises."""

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Return normalized capabilities."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
    ) -> ModelResult:
        """Run a completion and return a normalized ModelResult.

        Raises ProviderError subclasses on failure so the Router/Kernel can
        apply controlled fallback.
        """

    # ------------------------------------------------------------------
    # Helpers shared by adapters
    # ------------------------------------------------------------------
    def _measure(self, fn: Any) -> tuple[Any, int]:
        start = time.time()
        result = fn()
        elapsed = int((time.time() - start) * 1000)
        return result, elapsed