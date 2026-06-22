"""Genesis Protocol - Perplexity AI Provider

Perplexity Sonar models for research and real-time info.
"""

import os
import logging
from typing import List
from genesis_protocol.ai.providers.base_provider import (
    BaseProvider,
    ProviderCapability,
    AIRequest,
    AIResponse,
)

logger = logging.getLogger("ai.providers.perplexity")


class PerplexityProvider(BaseProvider):
    """Perplexity AI provider."""

    def __init__(self):
        """Initialize Perplexity provider."""
        super().__init__("perplexity")
        self.api_key = os.environ.get("PERPLEXITY_API_KEY")
        self.base_url = "https://api.perplexity.ai"

    async def generate(self, request: AIRequest) -> AIResponse:
        """Generate response using Perplexity API."""
        import aiohttp
        import time

        start_time = time.time()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": request.model or "sonar",
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.stream:
            payload["stream"] = True

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"Perplexity API error: {response.status} - {error_text}")

                    data = await response.json()

                    latency_ms = int((time.time() - start_time) * 1000)
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)

                    content = data["choices"][0]["message"]["content"]

                    return AIResponse(
                        content=content,
                        provider="perplexity",
                        model=data.get("model", request.model),
                        tokens_used=tokens_used,
                        latency_ms=latency_ms,
                        cost_estimate=self._estimate_cost(tokens_used, request.model),
                        finish_reason=data["choices"][0].get("finish_reason"),
                        raw_response=data,
                    )

        except Exception as e:
            self.record_failure()
            logger.error(f"Perplexity error: {e}")
            raise

    def is_configured(self) -> bool:
        """Check if Perplexity is configured."""
        return bool(self.api_key)

    def get_capabilities(self) -> List[ProviderCapability]:
        """Get Perplexity capabilities."""
        return [
            ProviderCapability.TEXT,
            ProviderCapability.FUNCTION_CALLING,
        ]

    def get_default_model(self) -> str:
        """Get default Perplexity model."""
        return "sonar"
