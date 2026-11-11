"""Genesis Protocol - Generic OpenAI-compatible provider.

Many vendors expose the OpenAI `/chat/completions` shape. This base class
centralises that call so a new provider only needs to declare its base URL,
env var, default model and display name.
"""

import time
from typing import Dict, List, Optional

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider, AIRequest, AIResponse, ProviderCapability, loop_safe_client,
)
from genesis_protocol.utils.logger import get_logger


class OpenAICompatibleProvider(BaseProvider):
    """Provider for any service exposing the OpenAI chat-completions API."""

    #: Subclasses override these.
    ENV_VAR: str = ""
    BASE_URL: str = ""
    DEFAULT_MODEL: str = ""
    EXTRA_HEADERS: Dict[str, str] = {}

    def __init__(self, name: str, env_var: str = None, base_url: str = None,
                 default_model: str = None, api_key: Optional[str] = None,
                 extra_headers: Dict[str, str] = None):
        super().__init__(name)
        import os
        self.logger = get_logger(f"ai.providers.{name}")
        self.api_key = api_key if api_key is not None else os.environ.get(env_var or self.ENV_VAR, "")
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.default_model = default_model or self.DEFAULT_MODEL
        self.timeout = 120
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        headers.update(self.EXTRA_HEADERS)
        headers.update(extra_headers or {})
        self._client_headers = headers if self.api_key else None

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def get_capabilities(self) -> List[ProviderCapability]:
        return [ProviderCapability.TEXT, ProviderCapability.FUNCTION_CALLING]

    def get_default_model(self) -> str:
        return self.default_model

    async def generate(self, request: AIRequest) -> AIResponse:
        if not self.should_use():
            raise Exception(f"{self.name} provider circuit is open")
        if not self.is_configured():
            raise Exception(f"{self.name} API key not configured")

        start = time.time()
        payload = {
            "model": request.model or self.default_model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stream:
            payload["stream"] = True

        try:
            client = loop_safe_client(
                self.name, base_url=self.base_url,
                headers=self._client_headers, timeout=self.timeout,
            )
            resp = await client.post("/chat/completions", json=payload)
            if resp.status_code != 200:
                raise Exception(f"{self.name} API error: {resp.status_code} - {resp.text[:200]}")
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            tokens = data.get("usage", {}).get("total_tokens", 0)
            self.record_success()
            return AIResponse(
                content=content,
                provider=self.name,
                model=data.get("model", payload["model"]),
                tokens_used=tokens,
                latency_ms=int((time.time() - start) * 1000),
                cost_estimate=self._estimate_cost(tokens, payload["model"]),
                finish_reason=data["choices"][0].get("finish_reason"),
                raw_response=data,
            )
        except Exception as e:
            self.record_failure()
            self.logger.error(f"{self.name} error: {e}")
            raise


class CerebrasProvider(OpenAICompatibleProvider):
    """Cerebras inference (fast gpt-oss models)."""
    ENV_VAR = "CEREBRAS_API_KEY"
    BASE_URL = "https://api.cerebras.ai/v1"
    DEFAULT_MODEL = "gpt-oss-120b"

    def __init__(self):
        super().__init__("cerebras")


class NvidiaProvider(OpenAICompatibleProvider):
    """NVIDIA NIM hosted models."""
    ENV_VAR = "NVIDIA_API_KEY"
    BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEFAULT_MODEL = "meta/llama-3.2-90b-vision-instruct"

    def __init__(self):
        super().__init__("nvidia")


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter multi-model gateway."""
    ENV_VAR = "OPENROUTER_API_KEY"
    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

    def __init__(self):
        super().__init__("openrouter",
                         extra_headers={"HTTP-Referer": "https://genesis-protocol.app",
                                        "X-Title": "Genesis Protocol"})


class OrcaRouterProvider(OpenAICompatibleProvider):
    """OrcaRouter gateway."""
    ENV_VAR = "ORCAROUTER_API_KEY"
    BASE_URL = "https://api.orcarouter.ai/v1"
    DEFAULT_MODEL = "qwen/qwen3.8-27b"

    def __init__(self):
        super().__init__("orcarouter")


class FreeAIProvider(OpenAICompatibleProvider):
    """Free.ai hosted models."""
    ENV_VAR = "FREEAI_API_KEY"
    BASE_URL = "https://api.free.ai/v1"
    DEFAULT_MODEL = "qwen7b"

    def __init__(self):
        super().__init__("freeai")
