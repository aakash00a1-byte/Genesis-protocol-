"""Genesis Protocol - Anthropic Claude Provider

Anthropic Claude AI integration.
"""

import time
from typing import List, Dict

from genesis_protocol.ai.providers.base_provider import (
    BaseProvider,
    AIRequest,
    AIResponse,
    ProviderCapability,
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.claude")


class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude AI provider.
    
    Supports Claude 3 and Claude 3.5 models.
    """
    
    API_URL = "https://api.anthropic.com/v1/messages"
    
    def __init__(self):
        """Initialize Claude provider."""
        super().__init__("claude")
        self._config = get_config()
        self._api_key = self._config.claude.api_key if hasattr(self._config, 'claude') else None
        self._version = "2023-06-01"
    
    def is_configured(self) -> bool:
        """Check if Claude is configured."""
        return bool(self._api_key)
    
    def get_capabilities(self) -> List[ProviderCapability]:
        """Get provider capabilities."""
        return [
            ProviderCapability.TEXT,
            ProviderCapability.VISION,
        ]
    
    def get_default_model(self) -> str:
        """Get default model."""
        return "claude-3-5-sonnet-20241022"
    
    def get_models(self) -> List[str]:
        """Get available models."""
        return [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]
    
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate response using Claude.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
        """
        start_time = time.time()
        
        if not self.is_configured():
            raise Exception("Claude API key not configured")
        
        if not self.should_use():
            raise Exception("Claude circuit breaker is OPEN")
        
        try:
            import httpx
            
            # Build messages for Claude format
            claude_messages = []
            for msg in request.messages:
                if msg.get("role") == "system":
                    # Claude uses system parameter
                    continue
                
                role = "user" if msg.get("role") == "user" else "assistant"
                claude_messages.append({
                    "role": role,
                    "content": msg.get("content", "")
                })
            
            # Get system prompt from first message if present
            system_prompt = None
            if request.messages and request.messages[0].get("role") == "system":
                system_prompt = request.messages[0].get("content")
                claude_messages = request.messages[1:]
            
            # Prepare request payload
            payload = {
                "model": request.model,
                "messages": claude_messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            }
            
            if system_prompt:
                payload["system"] = system_prompt
            
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": self._version,
                "content-type": "application/json",
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.API_URL,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code != 200:
                    error_msg = f"Claude API error: {response.status_code} - {response.text}"
                    logger.error(error_msg)
                    self.record_failure()
                    raise Exception(error_msg)
                
                data = response.json()
                
                # Extract response
                content = data.get("content", [{}])[0].get("text", "")
                usage = data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                total_tokens = input_tokens + output_tokens
                
                latency = int((time.time() - start_time) * 1000)
                
                self.record_success()
                
                logger.info(
                    "Claude response",
                    model=request.model,
                    latency_ms=latency,
                    tokens=total_tokens
                )
                
                return AIResponse(
                    content=content,
                    provider="claude",
                    model=request.model,
                    tokens_used=total_tokens,
                    latency_ms=latency,
                    finish_reason=data.get("stop_reason"),
                    raw_response=data
                )
                
        except Exception as e:
            logger.error(f"Claude generation failed: {e}")
            self.record_failure()
            raise