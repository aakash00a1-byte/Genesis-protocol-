"""Genesis Protocol - LLM Router

Intelligent model selection based on query analysis.
Selects the best model for each user request.
"""

import re
import logging
from typing import Optional, Dict, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger("ai.router")


class ModelCapability(Enum):
    """Model capabilities for routing."""
    CODING = "coding"
    CREATIVE = "creative"
    FAST = "fast"
    REASONING = "reasoning"
    LONG_CONTEXT = "long_context"
    VISION = "vision"
    CHEAP = "cheap"


@dataclass
class ModelInfo:
    """Model information for routing decisions."""
    name: str
    provider: str
    capabilities: List[ModelCapability]
    context_window: int
    priority: int = 0  # Higher = preferred for this task type


class LLMRouter:
    """
    Intelligent LLM Router for Genesis Protocol.
    
    Analyzes user queries and selects the best model based on:
    - Query type (coding, creative, fast, reasoning)
    - Context length requirements
    - Cost efficiency
    - Model availability
    """
    
    # Model definitions with capabilities
    MODELS: Dict[str, ModelInfo] = {
        # OpenAI Models
        "gpt-4o": ModelInfo(
            name="gpt-4o",
            provider="openai",
            capabilities=[ModelCapability.CODING, ModelCapability.REASONING, ModelCapability.VISION],
            context_window=128000,
            priority=3
        ),
        "gpt-4-turbo": ModelInfo(
            name="gpt-4-turbo",
            provider="openai",
            capabilities=[ModelCapability.CODING, ModelCapability.REASONING, ModelCapability.VISION],
            context_window=128000,
            priority=2
        ),
        "gpt-3.5-turbo": ModelInfo(
            name="gpt-3.5-turbo",
            provider="openai",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP],
            context_window=16385,
            priority=1
        ),
        
        # Anthropic Models
        "claude-sonnet-4-20250514": ModelInfo(
            name="claude-sonnet-4-20250514",
            provider="claude",
            capabilities=[ModelCapability.CREATIVE, ModelCapability.REASONING, ModelCapability.CODING],
            context_window=200000,
            priority=3
        ),
        "claude-3-5-sonnet-20241022": ModelInfo(
            name="claude-3-5-sonnet-20241022",
            provider="claude",
            capabilities=[ModelCapability.CREATIVE, ModelCapability.REASONING, ModelCapability.CODING],
            context_window=200000,
            priority=3
        ),
        "claude-3-haiku-20240307": ModelInfo(
            name="claude-3-haiku-20240307",
            provider="claude",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP],
            context_window=200000,
            priority=2
        ),
        
        # Google Models
        "gemini-2.0-flash": ModelInfo(
            name="gemini-2.0-flash",
            provider="gemini",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP, ModelCapability.LONG_CONTEXT],
            context_window=1000000,
            priority=3
        ),
        "gemini-1.5-pro": ModelInfo(
            name="gemini-1.5-pro",
            provider="gemini",
            capabilities=[ModelCapability.LONG_CONTEXT, ModelCapability.REASONING, ModelCapability.VISION],
            context_window=2000000,
            priority=4
        ),
        "gemini-1.5-flash": ModelInfo(
            name="gemini-1.5-flash",
            provider="gemini",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP, ModelCapability.VISION],
            context_window=1000000,
            priority=2
        ),
        
        # Groq Models (fallback)
        "llama-3.3-70b-versatile": ModelInfo(
            name="llama-3.3-70b-versatile",
            provider="groq",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP, ModelCapability.REASONING],
            context_window=32768,
            priority=2
        ),
        "mixtral-8x7b-32768": ModelInfo(
            name="mixtral-8x7b-32768",
            provider="groq",
            capabilities=[ModelCapability.FAST, ModelCapability.CHEAP],
            context_window=32768,
            priority=1
        ),
    }
    
    # Query patterns for classification
    CODING_PATTERNS = [
        r'\b(code|programming|python|javascript|java|c\+\+|rust|go|html|css|debug|function|class|api|sql|git|bug|error)\b',
        r'\b(write|create|build|make)\s+(a\s+)?(code|program|script|function|app|website)\b',
        r'\b(fix|debug|implement|develop)\b',
        r'```\w*',  # Code blocks
    ]
    
    CREATIVE_PATTERNS = [
        r'\b(story|write|poem|song|creative|imagine|storytelling|narrative)\b',
        r'\b(brainstorm|ideas|generate|creative)\b',
        r'\b(story|essay|article|blog|content|marketing)\b',
    ]
    
    REASONING_PATTERNS = [
        r'\b(explain|why|how|reason|logic|analyze|analyse|compare|contrast|think)\b',
        r'\b(what\s+is|define|meaning|understand|learn)\b',
        r'\b(because|therefore|since|hence|thus)\b',
        r'\b(pros|cons|advantages|disadvantages)\b',
    ]
    
    LONG_CONTEXT_PATTERNS = [
        r'\b(long|extended|detailed|comprehensive|thorough)\b',
        r'\b(summarize|summary|overview|brief)\b',
        r'\b(document|paper|article|book|report)\b',
        r'\b(history|background|context)\b',
    ]
    
    FAST_PATTERNS = [
        r'\b(quick|fast|simple|short|brief|quickly)\b',
        r'\b(hi|hello|hey|help|thanks|thank\s+you)\b',
        r'\?|!$',  # Short questions or exclamations
    ]
    
    def __init__(self):
        """Initialize LLM Router."""
        self.logger = logging.getLogger("ai.router")
        self.logger.info("LLM Router initialized")
    
    def classify_query(self, query: str) -> List[str]:
        """
        Classify query into categories.
        
        Args:
            query: User input text
            
        Returns:
            List of detected categories
        """
        query_lower = query.lower()
        categories = []
        
        # Check coding patterns
        for pattern in self.CODING_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                categories.append("coding")
                break
        
        # Check creative patterns
        for pattern in self.CREATIVE_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                categories.append("creative")
                break
        
        # Check reasoning patterns
        for pattern in self.REASONING_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                categories.append("reasoning")
                break
        
        # Check long context patterns
        for pattern in self.LONG_CONTEXT_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                categories.append("long_context")
                break
        
        # Check fast/simple patterns
        for pattern in self.FAST_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                categories.append("fast")
                break
        
        # Default to reasoning if no pattern matched
        if not categories:
            categories.append("reasoning")
        
        self.logger.debug(f"Query classified: {categories}")
        return categories
    
    def choose_model(self, user_input: str, preferred_provider: str = None) -> str:
        """
        Choose the best model for the given input.
        
        Args:
            user_input: User's query
            preferred_provider: Optional preferred provider
            
        Returns:
            Model name string
        """
        categories = self.classify_query(user_input)
        
        # If preferred provider specified, try that first
        if preferred_provider:
            model = self._get_best_for_provider(preferred_provider, categories)
            if model:
                self.logger.info(f"Model selected (preferred): {model} for categories: {categories}")
                return model
        
        # Route based on categories (in priority order)
        if "coding" in categories:
            model = self._route_coding()
        elif "creative" in categories:
            model = self._route_creative()
        elif "long_context" in categories:
            model = self._route_long_context()
        elif "reasoning" in categories:
            model = self._route_reasoning()
        elif "fast" in categories:
            model = self._route_fast()
        else:
            model = self._route_default()
        
        self.logger.info(f"Model selected: {model} for input: {user_input[:50]}...")
        return model
    
    def _route_coding(self) -> str:
        """Route to best coding model."""
        # Prefer OpenAI for coding
        return "gpt-4o"
    
    def _route_creative(self) -> str:
        """Route to best creative writing model."""
        # Prefer Claude for creative tasks
        return "claude-3-5-sonnet-20241022"
    
    def _route_long_context(self) -> str:
        """Route to best long context model."""
        # Gemini 1.5 Pro for long context
        return "gemini-1.5-pro"
    
    def _route_reasoning(self) -> str:
        """Route to best reasoning model."""
        # Try Gemini first, then OpenAI, then Claude
        return "gemini-2.0-flash"
    
    def _route_fast(self) -> str:
        """Route to fastest/cheapest model."""
        # Groq for speed
        return "llama-3.3-70b-versatile"
    
    def _route_default(self) -> str:
        """Default routing."""
        return "gemini-2.0-flash"
    
    def _get_best_for_provider(self, provider: str, categories: List[str]) -> Optional[str]:
        """Get best model for a specific provider."""
        provider_models = [
            (name, info) for name, info in self.MODELS.items()
            if info.provider == provider
        ]
        
        if not provider_models:
            return None
        
        # Return first available model from provider
        return provider_models[0][0]
    
    def get_provider_for_model(self, model: str) -> str:
        """Get provider name for a model."""
        model_info = self.MODELS.get(model)
        if model_info:
            return model_info.provider
        return "groq"  # Default fallback
    
    def get_fallback_chain(self, primary_model: str) -> List[str]:
        """
        Get fallback chain for a model.
        
        Fallback order: OpenAI → Gemini → Claude → Groq
        """
        chain = [primary_model]
        
        # Add fallbacks based on primary provider
        provider = self.get_provider_for_model(primary_model)
        
        if provider == "openai":
            chain.extend(["gemini-2.0-flash", "claude-3-5-sonnet-20241022", "llama-3.3-70b-versatile"])
        elif provider == "claude":
            chain.extend(["gemini-2.0-flash", "gpt-4o", "llama-3.3-70b-versatile"])
        elif provider == "gemini":
            chain.extend(["gpt-4o", "claude-3-5-sonnet-20241022", "llama-3.3-70b-versatile"])
        else:  # groq or unknown
            chain.extend(["gemini-2.0-flash", "gpt-4o", "claude-3-5-sonnet-20241022"])
        
        return chain


# Singleton instance
_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    """Get or create router singleton."""
    global _router
    if _router is None:
        _router = LLMRouter()
    return _router


def choose_model(user_input: str, preferred_provider: str = None) -> str:
    """
    Central function to choose best model.
    
    Args:
        user_input: User query
        preferred_provider: Optional preferred provider
        
    Returns:
        Best model name
    """
    return get_router().choose_model(user_input, preferred_provider)


def log_model_usage(model: str, query: str, success: bool):
    """Log model usage for debugging."""
    logger.info(f"MODEL_USAGE | model={model} | success={success} | query={query[:50]}...")