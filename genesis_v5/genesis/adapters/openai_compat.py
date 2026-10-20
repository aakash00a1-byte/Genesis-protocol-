"""OpenAI-compatible provider adapter.

Any provider exposing an OpenAI-compatible chat completions endpoint can be
addressed via configuration:
  GENESIS_OPENAI_COMPAT_BASE_URL, GENESIS_OPENAI_COMPAT_API_KEY,
  GENESIS_OPENAI_COMPAT_MODEL.
Disabled unless configured.
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
    with_wall_clock_timeout,
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


class OpenAICompatibleAdapter(Provider):
    name = "openai_compat"
    needs_credentials = True

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        base_url: str | None = None,
        api_key_env: str = "GENESIS_OPENAI_COMPAT_API_KEY",
        model_env: str = "GENESIS_OPENAI_COMPAT_MODEL",
        http_post=None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.base_url = base_url or os.getenv(
            "GENESIS_OPENAI_COMPAT_BASE_URL", ""
        )
        self._api_key = os.getenv(api_key_env)
        self._model = os.getenv(model_env, "default")
        self._http_post = http_post or default_post
        self._enabled = bool(self.base_url and self._api_key)
        if not self._enabled:
            logger.info("OpenAI-compatible adapter DISABLED")

    def health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DISABLED,
                ok=False,
                message="disabled: missing base_url or API key",
            )
        return ProviderHealth(
            provider=self.name, status=ProviderStatus.READY, ok=True
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            models=[self._model] if self._enabled else [],
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
                "OpenAI-compatible adapter disabled (missing config)",
                provider=self.name,
                fallback=True,
            )
        payload = {
            "model": model or self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        effective_timeout = timeout_seconds or self.timeout_seconds
        try:
            resp, latency = measure(
                lambda: with_wall_clock_timeout(
                    lambda: self._http_post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        timeout=effective_timeout,
                    ),
                    effective_timeout,
                    self.name,
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