"""NVIDIA Nemotron adapter.

Nemotron is served via NVIDIA's OpenAI-compatible inference endpoints
(https://build.nvidia.com). This adapter uses the documented OpenAI-compatible
chat completions shape `{"messages": [...]}` against a configurable base URL.
The API format is assumed from NVIDIA's published OpenAI-compatibility
documentation; it cannot be live-verified offline, so the adapter stays
DISABLED unless `NVIDIA_API_KEY` and `GENESIS_NEMOTRON_BASE_URL` are set.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from genesis.adapters.http_common import (
    error_for_status,
    safe_json,
    default_post,
    measure,
    normalize_error,
    normalize_response,
)
from genesis.core import ModelResult
from genesis.exceptions import ProviderUnavailable

from genesis.providers.base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"


class NemotronAdapter(Provider):
    name = "nemotron"
    needs_credentials = True

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        api_key_env: str = "NVIDIA_API_KEY",
        base_url: str | None = None,
        http_post=None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.api_key_env = api_key_env
        self.base_url = base_url or os.getenv(
            "GENESIS_NEMOTRON_BASE_URL", DEFAULT_BASE_URL
        )
        self._api_key = os.getenv(api_key_env)
        self._http_post = http_post or default_post
        self._enabled = bool(self._api_key)
        if not self._enabled:
            logger.info("Nemotron adapter DISABLED (missing %s)", api_key_env)

    def health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DISABLED,
                ok=False,
                message="disabled: missing NVIDIA_API_KEY",
            )
        return ProviderHealth(
            provider=self.name, status=ProviderStatus.READY, ok=True
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            models=["nemotron-4-340b"] if self._enabled else [],
            capabilities=[
                ModelCapability.CHAT,
                ModelCapability.CODE,
                ModelCapability.REASONING,
            ],
            max_context_tokens=32_768,
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
                "Nemotron adapter disabled (missing NVIDIA_API_KEY)",
                provider=self.name,
                fallback=True,
            )
        payload = {
            "model": model or "nemotron-4-340b",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            resp, latency = measure(
                lambda: self._http_post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=timeout_seconds or self.timeout_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise normalize_error(exc, self.name) from exc
        status = getattr(resp, "status_code", 200)
        if status != 200:
            raise error_for_status(self.name, int(status))
        data = safe_json(resp, self.name)
        result = normalize_response(
            self.name,
            payload["model"],
            data,
            text_path="choices.0.message.content",
        )
        result.latency_ms = latency
        return result