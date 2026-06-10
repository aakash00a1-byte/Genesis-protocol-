"""Genesis Protocol - OpenAI AI Provider

OpenAI API integration for GPT models.
"""

import time
from typing import List, Dict, Any

import httpx

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider, AIRequest, AIResponse, ProviderCapability
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.openai")


class OpenAIProvider(BaseProvider):
    """
    OpenAI AI provider implementation.
    
    Provides access to GPT-4 and GPT-4o models.
    """
    
    BASE_URL = "https://api.openai.com/v1"
    
    def __init__(self):
        """Initialize OpenAI provider."""
        super().__init__("openai")
        config = get_config()
        self.api_key = config.openai.api_key
        self.default_model = config.openai.default_model
        self.timeout = config.openai.timeout
        
        if self.api_key:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        else:
            self._client = None
    
    def is_configured(self) -> bool:
        """Check if OpenAI is configured."""
        return bool(self.api_key)
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """Get provider capabilities."""
        return [ProviderCapability.TEXT, ProviderCapability.VISION]
    
    def get_default_model(self) -> str:
        """Get default model."""
        return self.default_model
    
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using OpenAI API.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
        """
        if not self.should_use():
            raise Exception("OpenAI provider circuit is open")
        
        if not self.is_configured():
            raise Exception("OpenAI API key not configured")
        
        start_time = time.time()
        
        try:
            payload = {
                "model": request.model or self.default_model,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }
            
            response = await self._client.post("/chat/completions", json=payload)
            
            if response.status_code == 429:
                self.record_failure()
                raise Exception("OpenAI rate limit exceeded")
            
            if response.status_code != 200:
                self.record_failure()
                raise Exception(f"OpenAI API error: {response.status_code}")
            
            data = response.json()
            self.record_success()
            
            latency_ms = int((time.time() - start_time) * 1000)
            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            
            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            
            cost = self._estimate_cost(tokens_used, request.model)
            
            logger.info(
                "OpenAI response",
                model=request.model,
                tokens=tokens_used,
                latency_ms=latency_ms
            )
            
            return AIResponse(
                content=content,
                provider="openai",
                model=request.model or self.default_model,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                cost_estimate=cost,
                finish_reason=choices[0].get("finish_reason") if choices else None,
                raw_response=data,
            )
            
        except Exception as e:
            self.record_failure()
            logger.error(f"OpenAI generation failed: {e}")
            raise