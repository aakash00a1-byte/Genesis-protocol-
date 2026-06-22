"""Genesis Protocol - AI Provider Chain

Multi-LLM routing with scoring-based model selection.
Fallback: Best scored → 2nd best → 3rd → Groq (final)
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from genesis_protocol.ai.providers import (
    BaseProvider, GroqProvider, OpenAIProvider, 
    GeminiProvider, HuggingFaceProvider, AIRequest, AIResponse,
    DeepSeekProvider, MistralProvider
)
from genesis_protocol.ai.scoring_engine import get_scoring_engine
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
    intent_category: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    total_latency_ms: int = 0
    total_cost: float = 0.0


class ProviderChain:
    """
    Multi-LLM Provider Chain with scoring-based selection.
    
    - Uses ScoringEngine for dynamic model selection
    - Fallback chain: Best → 2nd → 3rd → Groq
    - No hardcoded primary model
    - Logs all requests for analysis
    """
    
    def __init__(self):
        """Initialize provider chain."""
        self._config = get_config()
        self._scoring = get_scoring_engine()
        
        # Initialize all providers equally
        self._providers: Dict[str, BaseProvider] = {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "claude": None,
            "groq": GroqProvider(),
            "huggingface": HuggingFaceProvider(),
            "deepseek": DeepSeekProvider(),
            "mistral": MistralProvider(),
        }
        
        # Initialize Claude if key available
        self._init_claude()
        
        # Base provider order (fallback priority)
        self._base_order = [
            "openai", "gemini", "claude", "deepseek", "mistral", "huggingface", "groq"
        ]
        
        # Request logging
        self._request_log: List[Dict] = []
        
        logger.info("Provider chain initialized (scoring-based)")
    
    def _init_claude(self):
        """Initialize Claude provider if API key available."""
        try:
            from genesis_protocol.ai.providers.claude_provider import ClaudeProvider
            self._providers["claude"] = ClaudeProvider()
            logger.info("Claude provider initialized")
        except Exception as e:
            logger.debug(f"Claude not available: {e}")
    
    async def call(self, messages: List[Dict[str, str]], 
                   preferred_provider: str = None,
                   model: str = None,
                   temperature: float = 0.7,
                   max_tokens: int = 1000,
                   user_input: str = None,
                   bypass_scoring: bool = False) -> AICallResult:
        """
        Make an AI call with scoring-based routing.
        """
        start_time = datetime.utcnow()
        attempts = 0
        errors = []
        
        # Get available providers
        available = self.get_available_providers()
        

        # Debug: log available providers
        logger.info(f"Available providers: {available}")
        for name, prov in self._providers.items():
            if prov:
                logger.info(f"Provider {name}: configured={prov.is_configured()}, should_use={prov.should_use()}")

        # If no providers available, return error
        if not available:
            logger.error("NO AI PROVIDERS CONFIGURED! Set GROQ_API_KEY in Railway.")
            return AICallResult(
                success=False,
                error="No AI providers configured. Please set GROQ_API_KEY environment variable.",
                attempts=0,
            )

        # Determine model and provider using scoring
        if model and preferred_provider:
            target_provider = preferred_provider
            target_model = model
        elif not bypass_scoring and user_input:
            target_provider, target_model, score, intent = self._scoring.select_model(
                user_input, available
            )
            logger.info(f"Scoring selected: {target_model} (score: {score:.2f}) for {intent.primary_intent}")
        else:
            target_provider = available[0] if available else "groq"
            target_model = model or self._providers[target_provider].get_default_model()
        
        # Build provider order: target → fallbacks
        providers_to_try = self._get_fallback_chain(target_provider, available)
        
        # Try each provider
        for provider_name in providers_to_try:
            provider = self._providers.get(provider_name)
            if not provider or not provider.is_configured():
                continue
            
            if not provider.should_use():
                errors.append(f"{provider_name}: circuit_open")
                continue
            
            attempts += 1
            
            # Map model to provider's available model
            model_to_use = self._map_model_to_provider(target_model, provider_name, provider)
            
            try:
                logger.info(f"Attempting: {provider_name}/{model_to_use}")
                
                request = AIRequest(
                    messages=messages,
                    model=model_to_use,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                
                response = await provider.generate(request)
                total_latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
                
                # Log successful request
                self._log_request(user_input or "", provider_name, model_to_use, "success", total_latency)
                
                return AICallResult(
                    success=True,
                    response=response,
                    provider_used=provider_name,
                    model_used=model_to_use,
                    intent_category=target_provider,
                    attempts=attempts,
                    total_latency_ms=total_latency,
                    total_cost=response.cost_estimate,
                )
                
            except Exception as e:
                error_str = str(e)
                errors.append(f"{provider_name}: {error_str}")
                logger.warning(f"{provider_name} failed: {error_str}")
                continue
        
        # All failed
        total_latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        self._log_request(user_input or "", target_provider, target_model, "failed", total_latency, errors=errors)
        
        return AICallResult(
            success=False,
            error=f"All providers failed: {'; '.join(errors)}",
            attempts=attempts,
            total_latency_ms=total_latency,
        )
    
    def _map_model_to_provider(self, model: str, provider: str, provider_obj) -> str:
        """Map router model to provider's actual model."""
        model_lower = model.lower()
        
        if provider == "openai" and ("gpt" in model_lower or "o" in model_lower):
            return model if model in ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini", "gpt-3.5-turbo"] else provider_obj.get_default_model()
        
        if provider == "gemini" and "gemini" in model_lower:
            return model

        
        if provider == "claude" and "claude" in model_lower:
            return model

        
        if provider == "groq" and ("llama" in model_lower or "mixtral" in model_lower):
            return model

        

        if provider == "deepseek" and "deepseek" in model_lower:
            return model


        if provider == "mistral" and "mistral" in model_lower:
            return model


            return model

        return provider_obj.get_default_model()
    
    def _get_fallback_chain(self, primary: str, available: List[str]) -> List[str]:
        """Build fallback chain: primary → 2nd best → 3rd → Groq."""
        chain = [primary]
        
        for prov in self._base_order:
            if prov in available and prov != primary and prov not in chain:
                chain.append(prov)
        
        if "groq" not in chain:
            chain.append("groq")
        elif chain[-1] != "groq":
            chain.remove("groq")
            chain.append("groq")
        
        return chain
    
    def _log_request(self, query: str, provider: str, model: str, status: str, latency: int, errors: List[str] = None):
        """Log request for analysis and improvement."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "query_preview": query[:100] if query else "",
            "provider": provider,
            "model": model,
            "status": status,
            "latency_ms": latency,
            "errors": errors or []
        }
        self._request_log.append(log_entry)
        
        if len(self._request_log) > 1000:
            self._request_log = self._request_log[-1000:]
    
    def get_request_log(self) -> List[Dict]:
        """Get request log for analysis."""
        return self._request_log
    
    def get_available_providers(self) -> List[str]:
        """Get list of configured and available providers."""
        return [
            name for name in self._base_order
            if name in self._providers 
            and self._providers[name] 
            and self._providers[name].is_configured()
        ]
    
    def get_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            name: provider.get_status() if provider else {"name": name, "configured": False}
            for name, provider in self._providers.items()
        }
    
    def reset_all_circuits(self):
        """Reset circuit breakers for all providers."""
        for provider in self._providers.values():
            if provider:
                provider.reset_circuit()
        logger.info("All provider circuits reset")


# Singleton
_provider_chain: Optional[ProviderChain] = None


def get_provider_chain() -> ProviderChain:
    """Get global provider chain instance."""
    global _provider_chain
    if _provider_chain is None:
        _provider_chain = ProviderChain()
    return _provider_chain