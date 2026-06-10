"""Genesis Protocol - Google Gemini AI Provider

Gemini API integration for multimodal LLM inference.
"""

import time
from typing import List, Dict, Any

import httpx

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider, AIRequest, AIResponse, ProviderCapability
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.gemini")


class GeminiProvider(BaseProvider):
    """
    Google Gemini AI provider implementation.
    
    Provides access to Gemini models with large context windows.
    """
    
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    
    def __init__(self):
        """Initialize Gemini provider."""
        super().__init__("gemini")
        config = get_config()
        self.api_key = config.gemini.api_key
        self.default_model = config.gemini.default_model
        self.timeout = config.gemini.timeout
        
        if self.api_key:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        else:
            self._client = None
    
    def is_configured(self) -> bool:
        """Check if Gemini is configured."""
        return bool(self.api_key)
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """Get provider capabilities."""
        return [ProviderCapability.TEXT, ProviderCapability.VISION]
    
    def get_default_model(self) -> str:
        """Get default model."""
        return self.default_model
    
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using Gemini API.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
        """
        if not self.should_use():
            raise Exception("Gemini provider circuit is open")
        
        if not self.is_configured():
            raise Exception("Gemini API key not configured")
        
        start_time = time.time()
        
        try:
            # Convert messages to Gemini format
            contents = self._convert_messages(request.messages)
            
            url = f"{self.BASE_URL}/models/{request.model or self.default_model}:generateContent"
            params = {"key": self.api_key}
            
            payload = {
                "contents": contents,
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_tokens,
                },
            }
            
            response = await self._client.post(url, json=payload, params=params)
            
            if response.status_code == 429:
                self.record_failure()
                raise Exception("Gemini rate limit exceeded")
            
            if response.status_code != 200:
                self.record_failure()
                raise Exception(f"Gemini API error: {response.status_code}")
            
            data = response.json()
            self.record_success()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract content
            candidates = data.get("candidates", [])
            content = ""
            tokens_used = 0
            
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    if "text" in part:
                        content += part["text"]
                
                usage = data.get("usageMetadata", {})
                tokens_used = usage.get("totalTokenCount", 0)
            
            cost = self._estimate_cost(tokens_used, request.model)
            
            logger.info(
                "Gemini response",
                model=request.model,
                tokens=tokens_used,
                latency_ms=latency_ms
            )
            
            return AIResponse(
                content=content,
                provider="gemini",
                model=request.model or self.default_model,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                cost_estimate=cost,
                finish_reason=candidates[0].get("finishReason") if candidates else None,
                raw_response=data,
            )
            
        except Exception as e:
            self.record_failure()
            logger.error(f"Gemini generation failed: {e}")
            raise
    
    def _convert_messages(self, messages: List[Dict[str, str]]) -> List[Dict]:
        """Convert OpenAI-style messages to Gemini format."""
        contents = []
        
        for msg in messages:
            role = msg.get("role", "user")
            
            # Map roles
            if role == "system":
                role = "user"
            elif role == "assistant":
                role = "model"
            else:
                role = "user"
            
            parts = []
            if "content" in msg:
                parts.append({"text": msg["content"]})
            
            contents.append({
                "role": role,
                "parts": parts,
            })
        
        return contents