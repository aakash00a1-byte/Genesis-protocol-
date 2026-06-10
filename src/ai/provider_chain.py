"""Genesis Protocol - AI Provider Chain

Intelligent fallback chain between multiple AI providers.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from genesis_protocol.ai.providers import (
    BaseProvider, GroqProvider, OpenAIProvider, 
    GeminiProvider, HuggingFaceProvider, AIRequest, AIResponse
)
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.provider_chain")


@dataclass
class AICallResult:
    """Result of an AI call attempt."""
    success: bool
    response: Optional[AIResponse] = None
    provider_used: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    total_latency_ms: int = 0
    total_cost: float = 0.0


class ProviderChain:
    """
    AI Provider Chain with intelligent fallback.
    
    Manages multiple AI providers and automatically falls back
    when a provider fails or is rate-limited.
    """
    
    def __init__(self):
        """Initialize provider chain."""
        self._config = get_config()
        
        # Initialize providers
        self._providers: Dict[str, BaseProvider] = {
            "groq": GroqProvider(),
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "huggingface": HuggingFaceProvider(),
        }
        
        # Get provider order from config
        self._provider_order = self._config.get_ai_provider_order()
        
        logger.info(f"Provider chain initialized with: {self._provider_order}")
    
    async def call(self, messages: List[Dict[str, str]], 
                   preferred_provider: str = None,
                   model: str = None,
                   temperature: float = 0.7,
                   max_tokens: int = 1000) -> AICallResult:
        """
        Make an AI call with automatic fallback.
        
        Args:
            messages: Chat messages
            preferred_provider: Preferred provider (optional)
            model: Model to use (optional)
            temperature: Temperature setting
            max_tokens: Maximum tokens
            
        Returns:
            AICallResult: Result of the call
        """
        start_time = datetime.utcnow()
        attempts = 0
        errors = []
        
        # Build provider order
        if preferred_provider and preferred_provider in self._providers:
            providers_to_try = [preferred_provider] + [
                p for p in self._provider_order if p != preferred_provider
            ]
        else:
            providers_to_try = self._provider_order
        
        # Try each provider
        for provider_name in providers_to_try:
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            
            if not provider.is_configured():
                logger.debug(f"Skipping {provider_name} - not configured")
                continue
            
            if not provider.should_use():
                logger.debug(f"Skipping {provider_name} - circuit open")
                errors.append(f"{provider_name}: circuit open")
                continue
            
            attempts += 1
            
            try:
                logger.info(f"Attempting AI call with {provider_name}")
                
                request = AIRequest(
                    messages=messages,
                    model=model or provider.get_default_model(),
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                
                response = await provider.generate(request)
                
                total_latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                logger.info(
                    f"AI call successful",
                    provider=provider_name,
                    attempts=attempts,
                    latency_ms=total_latency
                )
                
                return AICallResult(
                    success=True,
                    response=response,
                    provider_used=provider_name,
                    attempts=attempts,
                    total_latency_ms=total_latency,
                    total_cost=response.cost_estimate,
                )
                
            except Exception as e:
                error_str = str(e)
                errors.append(f"{provider_name}: {error_str}")
                logger.warning(f"{provider_name} failed: {error_str}")
                continue
        
        # All providers failed
        total_latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        logger.error(
            f"All AI providers failed",
            attempts=attempts,
            errors=errors
        )
        
        return AICallResult(
            success=False,
            error=f"All providers failed: {'; '.join(errors)}",
            attempts=attempts,
            total_latency_ms=total_latency,
        )
    
    async def call_with_vision(self, text: str, image_url: str = None,
                                image_base64: str = None) -> AICallResult:
        """
        Make a vision-capable AI call.
        
        Args:
            text: Text prompt
            image_url: URL of image
            image_base64: Base64 encoded image
            
        Returns:
            AICallResult: Result of the call
        """
        # Vision-capable providers
        vision_providers = ["openai", "gemini"]
        
        messages = [{"role": "user", "content": []}]
        
        if image_base64:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
            })
        elif image_url:
            messages[0]["content"].append({
                "type": "image_url", 
                "image_url": {"url": image_url}
            })
        
        messages[0]["content"].append({
            "type": "text",
            "text": text
        })
        
        # Try vision providers in order
        for provider_name in vision_providers:
            provider = self._providers.get(provider_name)
            if not provider or not provider.is_configured():
                continue
            
            try:
                from genesis_protocol.ai.providers.base_provider import ProviderCapability
                if ProviderCapability.VISION not in provider.get_capabilities():
                    continue
                
                request = AIRequest(
                    messages=messages,
                    model=provider.get_default_model(),
                    temperature=0.7,
                    max_tokens=1000,
                )
                
                response = await provider.generate(request)
                
                return AICallResult(
                    success=True,
                    response=response,
                    provider_used=provider_name,
                    attempts=1,
                    total_latency_ms=response.latency_ms,
                    total_cost=response.cost_estimate,
                )
                
            except Exception as e:
                logger.warning(f"Vision call failed with {provider_name}: {e}")
                continue
        
        return AICallResult(
            success=False,
            error="No vision-capable provider available",
        )
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all providers.
        
        Returns:
            Dictionary of provider statuses
        """
        return {
            name: provider.get_status() 
            for name, provider in self._providers.items()
        }
    
    def get_available_providers(self) -> List[str]:
        """Get list of configured and available providers."""
        return [
            name for name in self._provider_order
            if name in self._providers and self._providers[name].is_configured()
        ]
    
    def reset_all_circuits(self):
        """Reset circuit breakers for all providers."""
        for provider in self._providers.values():
            provider.reset_circuit()
        logger.info("All provider circuits reset")


# Global provider chain instance
_provider_chain: Optional[ProviderChain] = None


def get_provider_chain() -> ProviderChain:
    """Get global provider chain instance."""
    global _provider_chain
    if _provider_chain is None:
        _provider_chain = ProviderChain()
    return _provider_chain