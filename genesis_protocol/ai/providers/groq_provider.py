"""Genesis Protocol - Groq AI Provider

Groq API integration for fast LLM inference.
"""

import time
from typing import List, Dict, Any

import httpx

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider, AIRequest, AIResponse, ProviderCapability
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.groq")


class GroqProvider(BaseProvider):
    """
    Groq AI provider implementation.
    
    Provides fast LLM inference using Groq's API.
    """
    
    BASE_URL = "https://api.groq.com/openai/v1"
    
    def __init__(self):
        """Initialize Groq provider."""
        super().__init__("groq")
        config = get_config()
        self.api_key = config.groq.api_key
        self.default_model = config.groq.default_model
        self.timeout = config.groq.timeout
        
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
        """Check if Groq is configured."""
        return bool(self.api_key)
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """Get provider capabilities."""
        return [ProviderCapability.TEXT]
    
    def get_default_model(self) -> str:
        """Get default model."""
        return self.default_model
    
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using Groq API.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
        """
        if not self.should_use():
            raise Exception("Groq provider circuit is open")
        
        if not self.is_configured():
            raise Exception("Groq API key not configured")
        
        start_time = time.time()
        
        try:
            # Prepare request payload
            payload = {
                "model": request.model or self.default_model,
                "messages": request.messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": False,
            }
            
            # Make API call
            response = await self._client.post("/chat/completions", json=payload)
            
            if response.status_code == 429:
                self.record_failure()
                raise Exception("Groq rate limit exceeded")
            
            if response.status_code != 200:
                self.record_failure()
                raise Exception(f"Groq API error: {response.status_code}")
            
            data = response.json()
            
            # Record success
            self.record_success()
            
            # Calculate metrics
            latency_ms = int((time.time() - start_time) * 1000)
            usage = data.get("usage", {})
            tokens_used = usage.get("total_tokens", 0)
            
            # Extract response content
            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            
            # Estimate cost
            cost = self._estimate_cost(tokens_used, request.model)
            
            logger.info(
                "Groq response",
                model=request.model,
                tokens=tokens_used,
                latency_ms=latency_ms
            )
            
            return AIResponse(
                content=content,
                provider="groq",
                model=request.model or self.default_model,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                cost_estimate=cost,
                finish_reason=choices[0].get("finish_reason") if choices else None,
                raw_response=data,
            )
            
        except Exception as e:
            self.record_failure()
            logger.error(f"Groq generation failed: {e}")
            raise