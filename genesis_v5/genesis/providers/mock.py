"""Offline mock provider used by tests and offline mode.

It is deterministic, never contacts the network, and never requires
credentials. It is the default provider when `GENESIS_OFFLINE=true`.
"""
from __future__ import annotations

import time
from typing import Any

from genesis.core import ModelResult
from genesis.exceptions import ProviderUnavailable

from .base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)


class MockProvider(Provider):
    name = "mock"
    offline = True
    needs_credentials = False

    def __init__(self, *, timeout_seconds: float = 30.0, fail: bool = False) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self._fail = fail

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            status=ProviderStatus.READY if not self._fail else ProviderStatus.ERROR,
            ok=not self._fail,
            latency_ms=1,
            message="mock provider ready",
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            models=["mock-1"],
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.CODE,
                ModelCapability.REASONING,
                ModelCapability.PLANNING,
                ModelCapability.RESEARCH,
                ModelCapability.QA,
            ],
            max_context_tokens=8192,
            cost_per_1k_tokens=0.0,
            reliability=1.0,
            supports_streaming=False,
            needs_credentials=False,
            offline=True,
        )

    def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout_seconds: float | None = None,
    ) -> ModelResult:
        if self._fail:
            raise ProviderUnavailable(
                "mock provider forced failure",
                provider=self.name,
                retryable=True,
            )
        start = time.time()
        # Determin, offline echo that preserves prompt semantics for tests.
        output = f"[mock] {prompt}"
        latency = int((time.time() - start) * 1000)
        return ModelResult(
            provider=self.name,
            model=model or "mock-1",
            output=output,
            usage={"prompt_tokens": len(prompt.split()), "completion_tokens": 1},
            latency_ms=latency,
            status="success",
        )