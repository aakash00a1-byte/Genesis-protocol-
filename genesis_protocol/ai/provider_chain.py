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
    DeepSeekProvider, MistralProvider,
    CerebrasProvider, NvidiaProvider, OpenRouterProvider,
    OrcaRouterProvider, FreeAIProvider,
)
from genesis_protocol.ai.scoring_engine import get_scoring_engine
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.provider_chain")


# Token estimate divisor. Real English averages ~4 chars/token; dividing by 3
# over-estimates by ~25%, so the guard errs toward trimming or skipping rather
# than sending a prompt the provider will reject.
CHARS_PER_TOKEN = 3

# Documented input windows, in tokens. Only limits that were observed or
# documented are listed; anything else falls back to DEFAULT_CONTEXT_WINDOW.
CONTEXT_WINDOWS: Dict[str, int] = {
    # 400 from openrouter: "maximum context length is 131072 tokens"
    "openrouter": 131072,
    # 400 from freeai: "maximum context length is 32768 tokens"
    "freeai": 32768,
    # Gemini 2.5 Flash documented input limit
    "gemini": 1048576,
    # gpt-oss-120b on Groq
    "groq": 131072,
}
# Smallest limit observed in practice. Unknown providers are treated as small
# on purpose: under-estimating only skips a provider, over-estimating sends a
# prompt that fails.
DEFAULT_CONTEXT_WINDOW = 32768

# Room kept for the reply; output tokens count against the same window.
MIN_OUTPUT_RESERVE = 512

# AICallResult.failure_kind values, so callers can categorise without parsing
# the error text.
FAILURE_TOO_LARGE = "too_large"
FAILURE_UNAVAILABLE = "unavailable"


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
    failure_kind: Optional[str] = None


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
            "cerebras": CerebrasProvider(),
            "nvidia": NvidiaProvider(),
            "openrouter": OpenRouterProvider(),
            "orcarouter": OrcaRouterProvider(),
            "freeai": FreeAIProvider(),
        }
        
        # Initialize Claude if key available
        self._init_claude()
        
        # Base provider order (fallback priority)
        self._base_order = [
            "openai", "gemini", "claude", "deepseek", "mistral", "huggingface", "groq",
            "openrouter", "cerebras", "nvidia", "freeai", "orcarouter",
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
                failure_kind=FAILURE_UNAVAILABLE,
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
        
        # A message that cannot fit any window is a size problem, not a provider
        # problem. Walking the fallback chain would bury that behind "all
        # providers failed", so refuse up front with the real numbers.
        usable = [n for n in providers_to_try
                  if self._providers.get(n) is not None and self._providers[n].is_configured()]
        latest_content = messages[-1].get("content", "") if messages else ""
        latest_tokens = self._estimate_tokens(latest_content)
        largest_window = max(
            (self._context_window(n, self._providers[n]) for n in usable), default=0
        )
        if usable and latest_tokens + max(max_tokens, MIN_OUTPUT_RESERVE) > largest_window:
            error = (
                f"Message too large: ~{latest_tokens} tokens ({len(latest_content)} chars "
                f"at {CHARS_PER_TOKEN} chars/token), but the largest available context is "
                f"~{largest_window} tokens. Please split the message into smaller parts."
            )
            logger.error(error)
            self._log_request(user_input or "", target_provider, target_model, "failed", 0, errors=[error])
            return AICallResult(
                success=False,
                error=error,
                attempts=0,
                failure_kind=FAILURE_TOO_LARGE,
            )

        size_skips = 0

        # Try each provider
        for provider_name in providers_to_try:
            provider = self._providers.get(provider_name)
            if not provider or not provider.is_configured():
                continue

            if not provider.should_use():
                errors.append(f"{provider_name}: circuit_open")
                continue

            window = self._context_window(provider_name, provider)
            provider_messages, detail = self._fit_messages(messages, window, max_tokens)
            if provider_messages is None:
                size_skips += 1
                errors.append(
                    f"{provider_name}: prompt too large (~{detail} tokens, window {window})"
                )
                logger.info(f"Skipping {provider_name}: ~{detail} tokens exceeds {window}")
                continue
            if len(provider_messages) != len(messages):
                logger.info(
                    f"{provider_name}: dropped {len(messages) - len(provider_messages)} old "
                    f"message(s) to fit {window} tokens"
                )

            attempts += 1

            # Map model to provider's available model
            model_to_use = self._map_model_to_provider(target_model, provider_name, provider)

            try:
                logger.info(f"Attempting: {provider_name}/{model_to_use}")

                request = AIRequest(
                    messages=provider_messages,
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
                # A read timeout often carries no message at all, which used to
                # produce the useless "All providers failed: gemini: ". Fall
                # back to what the provider recorded, then to the type name.
                error_str = str(e) or provider.get_status().get("last_error") \
                    or type(e).__name__
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
            failure_kind=(FAILURE_TOO_LARGE if (size_skips and not attempts)
                          else FAILURE_UNAVAILABLE),
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Conservative token count: chars / CHARS_PER_TOKEN, never zero."""
        return max(1, len(text or "") // CHARS_PER_TOKEN)

    def _message_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Estimated prompt size of a whole message list."""
        return sum(self._estimate_tokens(m.get("content", "")) for m in messages)

    def _context_window(self, provider_name: str, provider) -> int:
        """Input window in tokens: provider declaration first, then the map."""
        declared = getattr(provider, "context_window", None)
        if isinstance(declared, int) and declared > 0:
            return declared
        return CONTEXT_WINDOWS.get(provider_name, DEFAULT_CONTEXT_WINDOW)

    def _fit_messages(self, messages: List[Dict[str, str]], window: int,
                      max_tokens: int):
        """Fit `messages` into `window`, dropping the oldest history first.

        Returns ``(messages_to_send, trimmed)`` or ``(None, tokens_needed)``
        when the newest message alone cannot fit. The newest message is never
        dropped or shortened: answering a truncated version of the question is
        worse than reporting that it is too large.
        """
        budget = window - max(max_tokens, MIN_OUTPUT_RESERVE)
        latest_tokens = self._estimate_tokens(
            messages[-1].get("content", "") if messages else ""
        )
        if latest_tokens > budget:
            return None, latest_tokens

        kept = list(messages)
        while len(kept) > 1 and self._message_tokens(kept) > budget:
            # Keep a leading system prompt; drop the oldest history entry.
            drop_at = 1 if kept[0].get("role") == "system" else 0
            if drop_at >= len(kept) - 1:
                break
            kept.pop(drop_at)

        if self._message_tokens(kept) > budget:
            return None, self._message_tokens(kept)
        return kept, len(kept) != len(messages)
    
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