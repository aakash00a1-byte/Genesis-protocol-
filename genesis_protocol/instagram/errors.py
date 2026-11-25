"""Typed failures for the Instagram publisher.

Every failure is a distinct type so a caller can decide what to do without
parsing strings, and so the retry layer never retries something that cannot
succeed (an expired token, a duplicate post, a denied approval).
"""
from __future__ import annotations


class InstagramError(Exception):
    """Base class for every Instagram failure."""


class ConfigurationError(InstagramError):
    """The module is not configured well enough to attempt anything."""


class UnknownAccountError(InstagramError):
    """No account matches the given id. Accounts are never guessed."""


class AccountDisabledError(InstagramError):
    """The account exists but is disabled; nothing may be published to it."""


class AccountInvalidError(InstagramError):
    """The account record itself is malformed (bad id, missing page id, ...)."""


class TokenUnavailableError(InstagramError):
    """No access token is configured for the account."""


class TokenExpiredError(InstagramError):
    """The access token is at or past its expiry. Not retryable."""


class ApprovalRequiredError(InstagramError):
    """Publishing needs an owner approval token; it is missing or invalid."""


class DuplicatePostError(InstagramError):
    """This exact content was already published (or is already queued)."""


class RateLimitedError(InstagramError):
    """A limit blocks this call. Transient ones may be retried later."""


class PublishingLimitReachedError(InstagramError):
    """Our own conservative daily cap is reached. Not retryable today."""


class ValidationError(InstagramError):
    """The post or its media cannot be published as described."""


class TransientError(InstagramError):
    """A network or server failure; safe to retry with backoff."""


class PermissionDeniedError(InstagramError):
    """The app or token lacks the permission this call needs."""


class ApiError(InstagramError):
    """Meta answered with an error payload we do not special-case."""

    def __init__(self, message: str, code: int | None = None, subcode: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode


class PublishFailedError(InstagramError):
    """Meta rejected the container or the publish call."""


class RetryExhaustedError(InstagramError):
    """Every retry attempt failed."""
