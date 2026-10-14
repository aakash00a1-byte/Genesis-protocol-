"""OpenHands SDK adapter.

The OpenHands SDK (https://docs.openhands.dev/sdk) is a Python framework for
building agents. The V5 SDK is a Python client (installed via pip
`openhands-ai`; see official docs). This adapter wraps the SDK's interface
only when the SDK package and an API key are available. Without them, the
adapter reports DISABLED and never fabricates success.

Because the precise SDK surface is version-dependent and cannot be verified
in this offline environment, the adapter isolates the SDK call behind the
`_infer` method using `getattr`, and gracefully disables when the package is
absent.
"""
from __future__ import annotations

import logging
from typing import Any

from genesis.core import ModelResult, now_ms
from genesis.exceptions import ProviderError, ProviderUnavailable

from genesis.providers.base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


class OpenHandsSDKAdapter(Provider):
    name = "openhandssdk"
    needs_credentials = True

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        api_key_env: str = "OPENHANDS_API_KEY",
        sdk_version: str | None = None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.api_key_env = api_key_env
        self._api_key = self._resolve_key()
        self._sdk = self._load_sdk()
        self._enabled = self._api_key is not None and self._sdk is not None
        if not self._enabled:
            logger.info(
                "OpenHands SDK adapter DISABLED "
                "(api_key=%s, sdk=%s)",
                self._api_key is not None,
                self._sdk is not None,
            )

    def _resolve_key(self) -> str | None:
        import os

        return os.getenv(self.api_key_env)

    def _load_sdk(self) -> Any:
        try:
            import openhands  # type: ignore[import-not-found]

            return openhands
        except Exception:  # noqa: BLE001
            return None

    def health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DISABLED,
                ok=False,
                message="disabled: missing SDK or API key",
            )
        return ProviderHealth(
            provider=self.name, status=ProviderStatus.READY, ok=True
        )

    def capabilities(self) -> ProviderCapabilities:
        caps = [
            ModelCapability.CODE,
            ModelCapability.AGENTIC,
            ModelCapability.CHAT,
            ModelCapability.REASONING,
        ]
        return ProviderCapabilities(
            provider=self.name,
            models=["openhands-default"] if self._enabled else [],
            capabilities=caps,
            max_context_tokens=128_000,
            cost_per_1k_tokens=0.0,
            reliability=0.9,
            supports_streaming=True,
            needs_credentials=True,
            offline=False,
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
        if not self._enabled:
            raise ProviderUnavailable(
                "OpenHands SDK adapter disabled (missing SDK or API key)",
                provider=self.name,
                fallback=True,
            )
        start = now_ms()
        try:
            output = self._infer(prompt, model=model)
        except Exception as exc:  # noqa: BLE001
            raise ProviderUnavailable(
                f"{self.name}: {exc}", provider=self.name,
                retryable=True, fallback=True,
            ) from exc
        return ModelResult(
            provider=self.name,
            model=model or "openhands-default",
            output=output,
            latency_ms=now_ms() - start,
            status="success",
        )

    def _infer(self, prompt: str, *, model: str | None) -> str:
        """Isolated SDK call — resolved lazily so adapters don't hard-wire
        to an unverified SDK surface."""
        sdk = self._sdk
        # Attempt the documented high-level entry points without assuming
        # a specific signature.
        if hasattr(sdk, "chat"):
            result = sdk.chat(prompt)
        elif hasattr(sdk, "complete"):
            result = sdk.complete(prompt)
        else:
            raise ProviderError(
                "OpenHands SDK installed but no supported inference entrypoint found"
            )
        if isinstance(result, str):
            return result
        return str(result)