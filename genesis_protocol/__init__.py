"""
Genesis Protocol - Autonomous Multimodal AI Agent v1.2

An autonomous AI agent system with Telegram interface that processes text,
voice, and image inputs through an intelligent multi-provider AI fallback chain.

The heavy submodules (``config`` needs python-dotenv, ``integration`` pulls in
the whole app) are exported lazily (PEP 562). Importing a leaf module such as
``genesis_protocol.updates`` must not drag in the rest of the application: the
self-improvement harness imports it with nothing but the standard library.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__version__ = "1.2.0"
__author__ = "Genesis Protocol Team"

_LAZY = {
    "Config": "genesis_protocol.config",
    "Message": "genesis_protocol.models",
    "User": "genesis_protocol.models",
    "Conversation": "genesis_protocol.models",
    "GenesisIntegration": "genesis_protocol.integration",
    "get_integration": "genesis_protocol.integration",
}

__all__ = [
    "Config", "Message", "User", "Conversation",
    "__version__",
    "GenesisIntegration", "get_integration",
]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from genesis_protocol.config import Config
    from genesis_protocol.integration import GenesisIntegration, get_integration
    from genesis_protocol.models import Conversation, Message, User


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
