"""Access-token handling: presence, expiry, rotation window and appsecret_proof.

Rules this module keeps:

* a token is read from the environment by the *name* recorded on the account,
  and its value is never returned to a caller that only wants status, never
  logged, and never written to disk;
* an expired or absent token stops publishing before any request is made,
  because Meta rejects it anyway and a retry cannot help;
* a token inside the rotation window is reported as such, so an owner rotates
  before a client's scheduled post fails;
* server-side calls can carry ``appsecret_proof``, the HMAC Meta documents for
  proving the call came from the backend that holds the app secret.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from .accounts import InstagramAccount
from .errors import TokenExpiredError, TokenUnavailableError
from .models import parse_iso

ROTATION_WINDOW_DAYS = 7


@dataclass(frozen=True)
class TokenInfo:
    """Status of one account's token. Never carries the token value."""

    account_id: str
    source: str
    present: bool
    expires_at: datetime | None = None
    days_left: float | None = None
    expired: bool = False
    needs_rotation: bool = False

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "source": self.source,
            "present": self.present,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "days_left": round(self.days_left, 1) if self.days_left is not None else None,
            "expired": self.expired,
            "needs_rotation": self.needs_rotation,
        }


def resolve_token(account: InstagramAccount, env: Mapping[str, str] | None = None) -> str:
    """Return the token value, or raise. This is the only accessor with the value."""
    source = env if env is not None else os.environ
    value = (source.get(account.token_env) or "").strip()
    if not value:
        raise TokenUnavailableError(
            f"account {account.account_id!r}: {account.token_env} is not set"
        )
    return value


def resolve_app_secret(
    account: InstagramAccount, env: Mapping[str, str] | None = None
) -> str:
    """Return the app secret, or "" when none is configured.

    Empty is allowed: Meta only requires ``appsecret_proof`` when the app has
    "Require App Secret" enabled, and the publisher documents that it is
    recommended rather than assumed.
    """
    source = env if env is not None else os.environ
    return (source.get(account.app_secret_env) or "").strip()


def appsecret_proof(app_secret: str, access_token: str) -> str:
    """HMAC-SHA256 of the access token keyed by the app secret."""
    return hmac.new(
        app_secret.encode("utf-8"), access_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def inspect_token(
    account: InstagramAccount,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> TokenInfo:
    """Report token presence and expiry without exposing the value."""
    moment = now or datetime.now(UTC)
    source = env if env is not None else os.environ
    present = bool((source.get(account.token_env) or "").strip())
    expires_at = parse_iso(account.token_expires_at) if account.token_expires_at else None
    days_left = None
    expired = False
    needs_rotation = False
    if expires_at is not None:
        days_left = (expires_at - moment).total_seconds() / 86400.0
        expired = days_left <= 0
        needs_rotation = 0 < days_left <= ROTATION_WINDOW_DAYS
    return TokenInfo(
        account_id=account.account_id,
        source=account.token_env,
        present=present,
        expires_at=expires_at,
        days_left=days_left,
        expired=expired,
        needs_rotation=needs_rotation,
    )


def assert_usable(
    account: InstagramAccount,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> TokenInfo:
    """Raise unless publishing may be attempted with this account's token."""
    info = inspect_token(account, env=env, now=now)
    if not info.present:
        raise TokenUnavailableError(
            f"account {account.account_id!r}: {account.token_env} is not set"
        )
    if info.expired:
        raise TokenExpiredError(
            f"account {account.account_id!r}: token expired at "
            f"{info.expires_at.isoformat() if info.expires_at else 'unknown'}; "
            "rotate it before publishing"
        )
    return info
