"""Genesis Protocol - HuggingFace AI Provider

HuggingFace Inference API integration for open models.
"""

import asyncio
import time
from typing import List, Dict, Any

import httpx

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider, AIRequest, AIResponse, ProviderCapability
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.huggingface")


class HuggingFaceProvider(BaseProvider):
    """
    HuggingFace AI provider implementation.
    
    Provides access to open models via HuggingFace Inference API.
    """
    
    BASE_URL = "https://api-inference.huggingface.co/models"
    
    def __init__(self):
        """Initialize HuggingFace provider."""
        super().__init__("huggingface")
        config = get_config()
        self.api_key = config.huggingface.api_key
        self.default_model = config.huggingface.default_model
        self.timeout = config.huggingface.timeout
        
        if self.api_key:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        else:
            self._client = None
    
    def is_configured(self) -> bool:
        """Check if HuggingFace is configured."""
        return bool(self.api_key)
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """Get provider capabilities."""
        return [ProviderCapability.TEXT]
    
    def get_default_model(self) -> str:
        """Get default model."""
        return self.default_model
    
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using HuggingFace Inference API.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
        """
        if not self.should_use():
            raise Exception("HuggingFace provider circuit is open")
        
        if not self.is_configured():
            raise Exception("HuggingFace API key not configured")
        
        start_time = time.time()
        
        try:
            # Convert messages to HF format
            prompt = self._convert_messages_to_prompt(request.messages)
            
            model = request.model or self.default_model
            url = f"{self.BASE_URL}/{model}"
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "temperature": request.temperature,
                    "max_new_tokens": request.max_tokens,
                    "return_full_text": False,
                },
                "options": {
                    "wait_for_model": True,  # Wait if model is loading
                },
            }
            
            response = await self._client.post(url, json=payload)
            
            if response.status_code == 503:
                # Model loading - try again after delay
                await asyncio.sleep(5)
                response = await self._client.post(url, json=payload)
            
            if response.status_code == 429:
                self.record_failure()
                raise Exception("HuggingFace rate limit exceeded")
            
            if response.status_code != 200:
                self.record_failure()
                raise Exception(f"HuggingFace API error: {response.status_code}")
            
            data = response.json()
            self.record_success()
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Extract content
            if isinstance(data, list) and len(data) > 0:
                content = data[0].get("generated_text", "")
            elif isinstance(data, dict):
                content = data.get("generated_text", "")
            else:
                content = str(data)
            
            # Estimate tokens (rough)
            tokens_used = len(prompt.split()) + len(content.split())
            
            # HF is free for many models, but estimate anyway
            cost = 0.0
            
            logger.info(
                "HuggingFace response",
                model=model,
                tokens=tokens_used,
                latency_ms=latency_ms
            )
            
            return AIResponse(
                content=content,
                provider="huggingface",
                model=model,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                cost_estimate=cost,
                raw_response=data,
            )
            
        except Exception as e:
            self.record_failure()
            logger.error(f"HuggingFace generation failed: {e}")
            raise
    
    def _convert_messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to a single prompt string."""
        prompt_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")
        
        prompt_parts.append("Assistant:")
        
        return "\n\n".join(prompt_parts)