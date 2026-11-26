"""Genesis Protocol - Base AI Provider

Abstract base class for all AI providers.
"""

import json
import re
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import httpx

from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.providers.base")

# One HTTP client per event loop, per provider. httpx.AsyncClient binds to the
# loop that first uses it; a client created once in __init__ then reused from a
# new loop (e.g. the webhook builds a fresh loop per request) fails with
# "Event loop is closed". Keying by the running loop avoids that.
_clients_by_loop: "Dict[tuple[str, int], httpx.AsyncClient]" = {}

# get_status() is served by /api/diagnostics, so error text is trimmed and any
# credential-shaped fragment is removed before it is stored.
LAST_ERROR_MAX_CHARS = 200
# Provider error bodies carry account, plan and request-identifier detail that
# does not belong in a status field; only the human message survives.
JSON_MESSAGE_MAX_CHARS = 120
_JSON_PAYLOAD = re.compile(r"\{.*\}", re.S)
# Account-level detail ("you need a subscription", "out of credits") says
# nothing about the request and describes the owner's billing state, so it is
# replaced by a neutral category instead of being echoed.
_BILLING_TERMS = re.compile(
    r"(?i)\b(subscription|billing|billed|credit|credits|payment|invoice|"
    r"upgrade|quota|top[- ]?up|plan)\b"
)
_BILLING_SUMMARY = "(provider rejected the request: plan or billing restriction)"
_SECRET_PATTERNS = (
    # The value usually follows the keyword after one more word
    # ("Authorization: Bearer abc"), so take up to two tokens.
    re.compile(r"(?i)\b(bearer|authorization|api[-_]?key|x-api-key|secret[-_]?token)\b\s*[:=]?\s*\S+(?:\s+\S+)?"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"\b(key|token|secret)=[^&\s]+"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),
)


def _json_message(blob: str) -> Optional[str]:
    """The one human-readable message inside a provider JSON body, if any."""
    try:
        data = json.loads(blob)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict):
        for key in ("message", "detail"):
            if isinstance(error.get(key), str) and error[key].strip():
                return error[key].strip()
    for key in ("message", "detail", "title"):
        if isinstance(data.get(key), str) and data[key].strip():
            return data[key].strip()
    return None


def sanitize_error(error: Optional[str]) -> Optional[str]:
    """Short, credential-free error text for provider status.

    A raw provider body ("402 - {...account, plan, request id...}") is reduced
    to its message so the status field cannot leak billing or account detail.
    """
    if not error:
        return None
    text = str(error)

    def _replace(match: "re.Match[str]") -> str:
        message = _json_message(match.group(0))
        if not message:
            return "(details withheld)"
        if _BILLING_TERMS.search(message):
            return _BILLING_SUMMARY
        return f"({message[:JSON_MESSAGE_MAX_CHARS]})"

    text = _JSON_PAYLOAD.sub(_replace, text)
    if _BILLING_SUMMARY not in text and _BILLING_TERMS.search(text):
        head = text.split(" - ", 1)[0]
        text = f"{head} - {_BILLING_SUMMARY}" if head != text else _BILLING_SUMMARY
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    text = " ".join(text.split())
    return text[:LAST_ERROR_MAX_CHARS] or None


def loop_safe_client(
    name: str,
    *,
    base_url: str | None = None,
    headers: Dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.AsyncClient:
    """Return an AsyncClient bound to the *current* event loop.

    Reuses the client across calls within the same loop and creates a new one
    when the loop changes (or the old loop has closed), so providers stay usable
    from short-lived loops.
    """
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = (name, id(loop))
    client = _clients_by_loop.get(key)
    if client is not None and not getattr(client, "is_closed", False):
        return client
    kwargs: Dict[str, Any] = {}
    if base_url is not None:
        kwargs["base_url"] = base_url
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    client = httpx.AsyncClient(**kwargs)
    _clients_by_loop[key] = client
    return client


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
        self._last_error: Optional[str] = None
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
        self._last_error = None
        if self._circuit_state == CircuitState.HALF_OPEN:
            self._circuit_state = CircuitState.CLOSED
            logger.info(f"{self.name} circuit CLOSED after recovery")
    
    def record_failure(self, error: Optional[str] = None):
        """Record failed call.

        `error` is what the next caller sees in get_status(). When it is not
        given, the exception being handled is used, so the many
        `except Exception: self.record_failure(); raise` sites need no change.
        """
        self._failures += 1
        self._last_failure_time = datetime.utcnow()
        if error is None:
            exc = sys.exc_info()[1]
            error = f"{type(exc).__name__}: {exc}" if exc is not None else None
        self._last_error = sanitize_error(error)
        
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
            "last_error": self._last_error,
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
            "gemini-2.5-flash": 0.075,
            "gemini-2.5-pro": 1.25,
        }
        
        rate = costs.get(model, 0.50)
        return (tokens / 1_000_000) * rate