"""Genesis Protocol - Security Module.

Exports are resolved lazily (PEP 562) so a stdlib-only leaf such as
``commit_signing`` can be imported without pulling in ``config`` -> ``dotenv``.
An eager import here made every leaf unimportable on a runner that does not
install the product's dependencies.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "AuthManager",
    "RateLimitMiddleware",
    "EncryptionService",
    "EncryptionUnavailableError",
]

_LAZY = {
    "AuthManager": ("genesis_protocol.security.auth", "AuthManager"),
    "RateLimitMiddleware": ("genesis_protocol.security.auth", "RateLimitMiddleware"),
    "EncryptionService": ("genesis_protocol.security.encryption", "EncryptionService"),
    "EncryptionUnavailableError": (
        "genesis_protocol.security.encryption", "EncryptionUnavailableError"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY[name]
    except KeyError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
