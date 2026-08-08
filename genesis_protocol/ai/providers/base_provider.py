"""Genesis Protocol - Base AI Provider

Abstract base class for all AI providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.base")


class ProviderCapability(Enum):
    """Capabilities of AI providers."""
    TEXT = "text"
    VISION = "vision"
    FUNCTION_CALLING = "function_calling"
    STREAMING = "streaming"


@dataclass
class AIRequest:
    """AI request payload."""
    messages: List[Dict[str, str]]
    model: str
    temperature: float = 0.7
    max_tokens: int = 1000
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIResponse:
    """AI response data."""
    content: str
    provider: str
    model: str
    tokens_used: int
    latency_ms: int
    cost_estimate: float = 0.0
    finish_reason: Optional[str] = None
    raw_response: Optional[Dict] = None


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class BaseProvider(ABC):
    """
    Abstract base class for AI providers.
    
    All AI providers must implement this interface.
    """
    
    def __init__(self, name: str):
        """
        Initialize provider.
        
        Args:
            name: Provider name (groq, openai, etc.)
        """
        self.name = name
        self._circuit_state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time: Optional[datetime] = None
        self._failure_threshold = 5
        self._recovery_timeout = 60  # seconds
        
        logger.info(f"Initialized {name} provider")
    
    @abstractmethod
    async def generate(self, request: AIRequest) -> AIResponse:
        """
        Generate AI response.
        
        Args:
            request: AI request
            
        Returns:
            AIResponse: Generated response
            
        Raises:
            Exception: If generation fails
        """
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if provider is properly configured.
        
        Returns:
            bool: True if configured
        """
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[ProviderCapability]:
        """
        Get provider capabilities.
        
        Returns:
            List of capabilities
        """
        pass
    
    @abstractmethod
    def get_default_model(self) -> str:
        """
        Get default model for provider.
        
        Returns:
            Model name
        """
        pass
    
    def should_use(self) -> bool:
        """
        Check if provider should be used (circuit breaker).
        
        Returns:
            bool: True if provider is available
        """
        if self._circuit_state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                if elapsed > self._recovery_timeout:
                    self._circuit_state = CircuitState.HALF_OPEN
                    logger.info(f"{self.name} moving to HALF_OPEN state")
                    return True
            return False
        return True
    
    def record_success(self):
        """Record successful call."""
        self._failures = 0
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_state = CircuitState.CLOSED
            logger.info(f"{self.name} circuit CLOSED after recovery")
    
    def record_failure(self):
        """Record failed call."""
        self._failures += 1
        self._last_failure_time = datetime.utcnow()
        
        if self._failures >= self._failure_threshold:
            self._circuit_state = CircuitState.OPEN
            logger.warning(f"{self.name} circuit OPENED after {self._failures} failures")
    
    def reset_circuit(self):
        """Reset circuit breaker."""
        self._circuit_state = CircuitState.CLOSED
        self._failures = 0
        self._last_failure_time = None
        logger.info(f"{self.name} circuit RESET")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get provider status.
        
        Returns:
            Status dictionary
        """
        return {
            "name": self.name,
            "configured": self.is_configured(),
            "circuit_state": self._circuit_state.value,
            "failures": self._failures,
            "capabilities": [c.value for c in self.get_capabilities()],
        }
    
    def _estimate_cost(self, tokens: int, model: str) -> float:
        """
        Estimate API cost.
        
        Args:
            tokens: Tokens used
            model: Model name
            
        Returns:
            Estimated cost in USD
        """
        # Rough cost estimates per 1M tokens
        costs = {
            "llama-3.1-70b-versatile": 0.70,
            "llama-3.1-8b-instant": 0.20,
            "gpt-4o-mini": 0.15,
            "gpt-4o": 5.00,
            "gemini-1.5-flash": 0.075,
            "gemini-1.5-pro": 1.25,
        }
        
        rate = costs.get(model, 0.50)
        return (tokens / 1_000_000) * rate