"""Register default adapters into the ProviderFactory.

Adapters are created lazily; disabled adapters report DISABLED via health()
and never fabricate success. Kept separate from the factory module to avoid
import cycles (adapters import providers.base).
"""
from __future__ import annotations

import logging

from genesis.providers.factory import get_factory

logger = logging.getLogger(__name__)

_REGISTERED = False


def register_default_adapters() -> None:
    """Idempotently register all shipped adapters."""
    global _REGISTERED
    if _REGISTERED:
        return
    from .claude import ClaudeAdapter
    from .gemini import GeminiAdapter
    from .local import LocalModelAdapter
    from .nemotron import NemotronAdapter
    from .openai_compat import OpenAICompatibleAdapter
    from .openhands import OpenHandsSDKAdapter

    factory = get_factory()
    factory.register("openhandssdk", OpenHandsSDKAdapter)
    factory.register("nemotron", NemotronAdapter)
    factory.register("openai_compat", OpenAICompatibleAdapter)
    factory.register("gemini", GeminiAdapter)
    factory.register("claude", ClaudeAdapter)
    factory.register("local", LocalModelAdapter)
    _REGISTERED = True