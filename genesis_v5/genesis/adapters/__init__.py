"""Genesis V5 provider adapters.

Every adapter is configuration-driven and stays DISABLED until its
configuration (endpoint + credentials) is verified present. No adapter
fabricates success. The offline MockProvider is the only provider active by
default.
"""
from __future__ import annotations

from .openhands import OpenHandsSDKAdapter
from .nemotron import NemotronAdapter
from .openai_compat import OpenAICompatibleAdapter
from .gemini import GeminiAdapter
from .claude import ClaudeAdapter
from .local import LocalModelAdapter
from .registration import register_default_adapters

__all__ = [
    "OpenHandsSDKAdapter",
    "NemotronAdapter",
    "OpenAICompatibleAdapter",
    "GeminiAdapter",
    "ClaudeAdapter",
    "LocalModelAdapter",
    "register_default_adapters",
]