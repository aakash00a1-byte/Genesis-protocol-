"""Central security configuration for the web application.

Production must be configured explicitly. A missing or shipped-default secret
fails closed instead of silently falling back to a value that is public in the
source tree. Development and testing keep working local defaults so the app can
still be run and tested without a full secret store.
"""
from __future__ import annotations

import os

# Values that ship in this repository and are therefore public. They must never
# be accepted in production.
PLACEHOLDER_SECRETS = frozenset(
    {
        "genesis-secret-key-change-in-production",
        "genesis-secret-key-2024",
        "genesis-autonomous-key",
        "genesis-admin-2024",
        "change-me",
        "changeme",
        "secret",
    }
)

# Production secrets must be long enough to resist guessing.
MIN_SECRET_LENGTH = 32

# Development fallbacks. Explicitly non-production only.
_DEV_SECRET_KEY = "genesis-dev-secret-key-not-for-production"
_DEV_MOBILE_TOKEN_SECRET = "genesis-dev-mobile-token-secret-not-for-production"


class InsecureConfigError(RuntimeError):
    """Raised when production security configuration is missing or unsafe."""


def is_production() -> bool:
    """True when GENESIS_ENV selects production."""
    return os.environ.get("GENESIS_ENV", "").strip().lower() == "production"


def _require_strong(name: str, value: str) -> str:
    if not value:
        raise InsecureConfigError(
            f"{name} is required in production and must be set explicitly."
        )
    if value in PLACEHOLDER_SECRETS:
        raise InsecureConfigError(
            f"{name} is set to a shipped default value; set a unique secret."
        )
    if len(value) < MIN_SECRET_LENGTH:
        raise InsecureConfigError(
            f"{name} must be at least {MIN_SECRET_LENGTH} characters in production."
        )
    return value


def resolve_secret_key() -> str:
    """Return the Flask session signing key.

    Production requires an explicit, strong SECRET_KEY. A new key is never
    generated, so sessions survive restarts only when the key is configured.
    """
    value = (os.environ.get("SECRET_KEY") or "").strip()
    if is_production():
        return _require_strong("SECRET_KEY", value)
    return value or _DEV_SECRET_KEY


def resolve_mobile_token_secret() -> str:
    """Return the HMAC key used to sign mobile Bearer tokens.

    Production requires a dedicated GENESIS_MOBILE_TOKEN_SECRET. There is no
    unsigned or per-restart-random fallback: every token is signed, and in
    production the key is stable and explicit.
    """
    value = (os.environ.get("GENESIS_MOBILE_TOKEN_SECRET") or "").strip()
    if is_production():
        return _require_strong("GENESIS_MOBILE_TOKEN_SECRET", value)
    return value or _DEV_MOBILE_TOKEN_SECRET


def resolve_admin_bootstrap_password() -> str | None:
    """Return the password for creating the first administrator, or None.

    ``None`` means "do not auto-provision an admin" and is only ever returned
    outside production. In production a missing or shipped-default
    ADMIN_PASSWORD raises, so a deploy cannot silently create an admin with a
    guessable password. An existing admin is never overwritten by the caller.
    """
    value = (os.environ.get("ADMIN_PASSWORD") or "").strip()
    if value in PLACEHOLDER_SECRETS:
        raise InsecureConfigError(
            "ADMIN_PASSWORD is set to a shipped default value; set a unique password."
        )
    if not value:
        if is_production():
            _require_strong("ADMIN_PASSWORD", value)
        return None
    if is_production():
        return _require_strong("ADMIN_PASSWORD", value)
    return value
