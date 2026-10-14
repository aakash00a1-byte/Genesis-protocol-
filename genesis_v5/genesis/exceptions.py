"""Genesis V5 exception hierarchy."""
from __future__ import annotations


class GenesisError(Exception):
    """Base error for the Genesis system."""


class PermissionDenied(GenesisError):
    """Raised when an operation is rejected by policy."""


class ToolExecutionError(GenesisError):
    """Raised when a tool fails or violates the sandbox."""


class SandboxViolation(ToolExecutionError):
    """Raised when a tool attempts to escape its sandbox boundary."""


class ToolTimeout(ToolExecutionError):
    """Raised when a tool exceeds its execution timeout."""


class MemoryError_(GenesisError):
    """Raised when memory operations fail and graceful failure is disabled."""


class ProviderError(GenesisError):
    """Raised when a provider cannot service a request."""

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
        fallback: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.fallback = fallback


class ProviderRateLimited(ProviderError):
    """Raised when a provider reports a rate limit condition."""


class ProviderTimeout(ProviderError):
    """Raised when a provider call exceeds its timeout."""


class ProviderUnavailable(ProviderError):
    """Raised when a provider cannot be reached or lacks credentials."""


class CircularDependencyError(GenesisError):
    """Raised when a task DAG contains a cycle."""


class RetryLimitExceeded(GenesisError):
    """Raised when bounded retries are exhausted."""


class ValidationError(GenesisError):
    """Raised when an input or output fails validation."""


class RateLimitExceeded(GenesisError):
    """Raised when a caller exceeds the configured rate limit."""