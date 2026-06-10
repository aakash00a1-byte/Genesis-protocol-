"""Genesis Protocol - Logging System

Structured logging with context support for Genesis Protocol.
"""

import logging
import sys
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Dict, Any

import structlog

from genesis_protocol.config import get_config


def setup_logging(level: str = None) -> None:
    """
    Setup structured logging for Genesis Protocol.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    config = get_config()
    log_level = level or config.app_log_level or "INFO"
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if config.app_env.value == "production" 
                else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Bound logger instance
    """
    logger_name = name or "genesis_protocol"
    return structlog.get_logger(logger_name)


@contextmanager
def LogContext(**kwargs: Any):
    """
    Context manager for adding temporary context to logs.
    
    Usage:
        with LogContext(user_id=123, action="process"):
            logger.info("Processing message")
    
    Args:
        **kwargs: Context key-value pairs
    """
    logger = get_logger()
    token = structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield logger
    finally:
        structlog.contextvars.unbind_contextvars(*kwargs.keys())


class GenesisLogger:
    """
    Genesis Protocol logger with component-specific logging.
    
    Provides organized logging for different system components.
    """
    
    def __init__(self, component: str):
        """
        Initialize component logger.
        
        Args:
            component: Component name (e.g., "ai.router", "bot.handlers")
        """
        self.component = component
        self._logger = get_logger(component)
    
    def debug(self, message: str, **kwargs: Any):
        """Log debug message."""
        self._logger.debug(message, component=self.component, **kwargs)
    
    def info(self, message: str, **kwargs: Any):
        """Log info message."""
        self._logger.info(message, component=self.component, **kwargs)
    
    def warning(self, message: str, **kwargs: Any):
        """Log warning message."""
        self._logger.warning(message, component=self.component, **kwargs)
    
    def error(self, message: str, **kwargs: Any):
        """Log error message."""
        self._logger.error(message, component=self.component, **kwargs)
    
    def critical(self, message: str, **kwargs: Any):
        """Log critical message."""
        self._logger.critical(message, component=self.component, **kwargs)
    
    def log_request(self, provider: str, model: str, tokens: int, latency_ms: int):
        """Log AI request."""
        self.info(
            "AI request completed",
            provider=provider,
            model=model,
            tokens=tokens,
            latency_ms=latency_ms
        )
    
    def log_error(self, error: Exception, context: str = None, **kwargs: Any):
        """Log exception with context."""
        self.error(
            str(error),
            error_type=type(error).__name__,
            context=context,
            **kwargs
        )
    
    def log_startup(self, component: str, config: dict = None):
        """Log component startup."""
        self.info(
            f"{component} started",
            config=config or {}
        )
    
    def log_shutdown(self, component: str):
        """Log component shutdown."""
        self.info(f"{component} stopped")
    
    def log_message(self, direction: str, message_id: str, chat_id: int, 
                    message_type: str = "text"):
        """Log message processing."""
        self.debug(
            f"Message {direction}",
            message_id=message_id,
            chat_id=chat_id,
            message_type=message_type
        )


# Component loggers
AI_LOGGER = GenesisLogger("ai")
BOT_LOGGER = GenesisLogger("bot")
MEMORY_LOGGER = GenesisLogger("memory")
PROCESSORS_LOGGER = GenesisLogger("processors")
INTEGRATIONS_LOGGER = GenesisLogger("integrations")
SECURITY_LOGGER = GenesisLogger("security")