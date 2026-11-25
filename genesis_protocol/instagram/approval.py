"""Owner approval gate for real publishing.

Requirement: nothing is published publicly without the owner saying so. A bare
boolean in a request body is not approval - anyone who can reach the code path
could set it. So approval is a short-lived HMAC token that only a holder of the
approval secret can mint, and that is bound to the exact account and the exact
content:

    v1.<expiry-unix>.<hmac-sha256-hex>

Binding matters: an approval for "acme-cafe, this caption, these images" cannot
be replayed for a different caption, a different image or another client's
account, and it stops working when it expires.

The gate fails closed. No secret configured means publishing is refused, not
permitted, because a missing secret is indistinguishable from an unapproved
caller.
"""
from __future__ import annotations

import hmac
import os
import time
from dataclasses import dataclass
from hashlib import sha256

from .errors import ApprovalRequiredError

APPROVAL_SECRET_ENV = "IG_APPROVAL_SECRET"
DEFAULT_TTL_SECONDS = 900


def _sign(secret: str, account_id: str, fingerprint: str, expires: int) -> str:
    message = f"v1|{account_id}|{fingerprint}|{expires}".encode()
    return hmac.new(secret.encode("utf-8"), message, sha256).hexdigest()


def mint_approval(
    secret: str,
    account_id: str,
    fingerprint: str,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Create an approval token for one account and one piece of content."""
    if not secret:
        raise ApprovalRequiredError("approval secret is not configured; cannot mint")
    moment = int(now if now is not None else time.time())
    expires = moment + max(1, int(ttl_seconds))
    return f"v1.{expires}.{_sign(secret, account_id, fingerprint, expires)}"


def verify_approval(
    secret: str,
    token: str,
    account_id: str,
    fingerprint: str,
    *,
    now: float | None = None,
) -> None:
    """Raise ``ApprovalRequiredError`` unless ``token`` authorises this publish."""
    if not secret:
        raise ApprovalRequiredError(
            f"{APPROVAL_SECRET_ENV} is not set; publishing is refused (fail closed)"
        )
    if not token:
        raise ApprovalRequiredError(
            "no owner approval token supplied; refusing to publish publicly"
        )
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "v1":
        raise ApprovalRequiredError("approval token is malformed")
    try:
        expires = int(parts[1])
    except ValueError as exc:
        raise ApprovalRequiredError("approval token has a bad expiry") from exc
    moment = int(now if now is not None else time.time())
    if expires <= moment:
        raise ApprovalRequiredError("approval token has expired; ask the owner again")
    expected = _sign(secret, account_id, fingerprint, expires)
    if not hmac.compare_digest(expected, parts[2]):
        raise ApprovalRequiredError(
            "approval token does not match this account and content"
        )


@dataclass(frozen=True)
class ApprovalGate:
    """Environment-backed gate: one secret, short-lived tokens."""

    secret: str = ""
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> ApprovalGate:
        source = env if env is not None else os.environ
        return cls(secret=(source.get(APPROVAL_SECRET_ENV) or "").strip())

    @property
    def configured(self) -> bool:
        return bool(self.secret)

    def mint(self, account_id: str, fingerprint: str, *, now: float | None = None) -> str:
        return mint_approval(
            self.secret, account_id, fingerprint, ttl_seconds=self.ttl_seconds, now=now
        )

    def require(self, token: str, account_id: str, fingerprint: str, *,
                now: float | None = None) -> None:
        verify_approval(self.secret, token, account_id, fingerprint, now=now)
