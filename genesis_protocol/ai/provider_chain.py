"""Genesis Protocol - AI Provider Chain

Intelligent fallback chain between multiple AI providers with LLM routing.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from genesis_protocol.ai.providers import (
    BaseProvider, GroqProvider, OpenAIProvider, 
    GeminiProvider, HuggingFaceProvider, AIRequest, AIResponse
)
from genesis_protocol.ai.llm_router import choose_model, get_router, log_model_usage
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.provider_chain")


@dataclass
class AICallResult:
    """Result of an AI call attempt."""
    success: bool
    response: Optional[AIResponse] = None
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    total_latency_ms: int = 0
    total_cost: float = 0.0


class ProviderChain:
    """
    AI Provider Chain with intelligent fallback and LLM routing.
    
    Manages multiple AI providers, uses smart model selection,
    and automatically falls back when a provider fails.
    """
    
    def __init__(self):
        """Initialize provider chain."""
        self._config = get_config()
        self._router = get_router()
        
        # Initialize providers (NO HARDCODE - all equal)
        self._providers: Dict[str, BaseProvider] = {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "claude": None,  # Will be initialized if available
            "groq": GroqProvider(),
            "huggingface": HuggingFaceProvider(),
        }
        
        # Try to initialize Claude if API key available
        self._init_claude()
        
        # Provider order: OpenAI -> Gemini -> Claude -> Groq -> HuggingFace
        self._provider_order = ["openai", "gemini", "claude", "groq", "huggingface"]
        
        # Remove None providers
        self._provider_order = [p for p in self._provider_order if self._providers.get(p)]
        
        logger.info(f"Provider chain initialized with: {self._provider_order}")
    
    def _init_claude(self):
        """Initialize Claude provider if API key available."""
        try:
            from genesis_protocol.ai.providers.claude_provider import ClaudeProvider
            self._providers["claude"] = ClaudeProvider()
            logger.info("Claude provider initialized")
        except Exception as e:
            logger.warning(f"Claude provider not available: {e}")
    
    async def call(self, messages: List[Dict[str, str]], 
                   preferred_provider: str = None,
                   model: str = None,
                   temperature: float = 0.7,
                   max_tokens: int = 1000,
                   user_input: str = None) -> AICallResult:
        """
        Make an AI call with intelligent routing and fallback.
        
        Args:
            messages: Chat messages
            preferred_provider: Preferred provider (optional)
            model: Specific model to use (optional - uses router if not set)
            temperature: Temperature setting
            max_tokens: Maximum tokens
            user_input: User's original query (for model selection)
            
        Returns:
            AICallResult: Result of the call
        """
        start_time = datetime.utcnow()
        attempts = 0
        errors = []
        
        # Smart model selection using LLM router
        if not model and user_input:
            model = choose_model(user_input)
            logger.info(f"Router selected model: {model}")
        
        # Build provider order (NEW FALLBACK: OpenAI → Gemini → Claude → Groq)
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
                # Smart model selection:
                # 1. If router selected a model AND provider matches, use it
                # 2. Otherwise, use provider's default model
                model_to_use = model if model else provider.get_default_model()
                
                # Map router models to provider defaults if not compatible
                # OpenAI only supports its own models
                if provider_name == "openai" and model_to_use not in ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini", "gpt-3.5-turbo"]:
                    model_to_use = provider.get_default_model()
                # Gemini only supports gemini models
                elif provider_name == "gemini" and "gemini" not in model_to_use and "gpt" not in model_to_use:
                    model_to_use = provider.get_default_model()
                # Claude only supports claude models
                elif provider_name == "claude" and "claude" not in model_to_use and "gemini" not in model_to_use:
                    model_to_use = provider.get_default_model()
                # Groq only supports llama/mixtral models
                elif provider_name == "groq" and "gemini" in model_to_use:
                    model_to_use = provider.get_default_model()
                
                logger.info(f"Attempting AI call with {provider_name} (model: {model_to_use})")
                
                request = AIRequest(
                    messages=messages,
                    model=model_to_use,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                
                response = await provider.generate(request)
                
                total_latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Log model usage
                log_model_usage(model_to_use, user_input or "", True)
                
                logger.info(
                    f"AI call successful",
                    provider=provider_name,
                    model=model_to_use,
                    attempts=attempts,
                    latency_ms=total_latency
                )
                
                return AICallResult(
                    success=True,
                    response=response,
                    provider_used=provider_name,
                    model_used=model_to_use,
                    attempts=attempts,
                    total_latency_ms=total_latency,
                    total_cost=response.cost_estimate,
                )
                
            except Exception as e:
                error_str = str(e)
                errors.append(f"{provider_name}: {error_str}")
                log_model_usage(model or "unknown", user_input or "", False)
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