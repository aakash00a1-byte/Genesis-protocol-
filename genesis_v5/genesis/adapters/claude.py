"""Claude (Anthropic Messages API) adapter.

Uses the documented Anthropic Messages API shape (x-api-key header,
/chat-completions-compatible fallback not assumed). Disabled unless
`ANTHROPIC_API_KEY` is present.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from genesis.adapters.http_common import (
    default_post,
    measure,
    normalize_error,
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

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"


class ClaudeAdapter(Provider):
    name = "claude"
    needs_credentials = True

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        base_url: str | None = None,
        api_key_env: str = "ANTHROPIC_API_KEY",
        model_env: str = "GENESIS_CLAUDE_MODEL",
        http_post=None,
    ) -> None:
        super().__init__(timeout_seconds=timeout_seconds)
        self.base_url = base_url or os.getenv(
            "GENESIS_CLAUDE_BASE_URL", DEFAULT_BASE_URL
        )
        self._api_key = os.getenv(api_key_env)
        self._model = os.getenv(model_env, "claude-sonnet-4-5")
        self._http_post = http_post or default_post
        self._enabled = bool(self._api_key)
        if not self._enabled:
            logger.info("Claude adapter DISABLED (missing %s)", api_key_env)

    def health(self) -> ProviderHealth:
        if not self._enabled:
            return ProviderHealth(
                provider=self.name,
                status=ProviderStatus.DISABLED,
                ok=False,
                message="disabled: missing ANTHROPIC_API_KEY",
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
            max_context_tokens=200_000,
            cost_per_1k_tokens=0.0,
            reliability=0.95,
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
                "Claude adapter disabled (missing ANTHROPIC_API_KEY)",
                provider=self.name,
                fallback=True,
            )
        payload = {
            "model": model or self._model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            resp, latency = measure(
                lambda: self._http_post(
                    f"{self.base_url}/messages",
                    json=payload,
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    timeout=timeout_seconds or self.timeout_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001
            raise normalize_error(exc, self.name) from exc
        if getattr(resp, "status_code", 200) != 200:
            raise normalize_error(
                ProviderUnavailable(
                    f"{self.name}: HTTP {getattr(resp, 'status_code', '?')}",
                    provider=self.name,
                ),
                self.name,
            )
        data = resp.json()
        content = data.get("content") or []
        text = ""
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text += block.get("text", "")
        usage = data.get("usage") or {}
        return ModelResult(
            provider=self.name,
            model=payload["model"],
            output=text,
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                ),
            },
            latency_ms=latency,
            status="success",
        )