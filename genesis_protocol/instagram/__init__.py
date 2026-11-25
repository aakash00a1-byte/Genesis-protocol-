"""Instagram professional-account publishing for Genesis.

Scope: publishing content (image, video, reel, story, carousel) to an Instagram
professional account through Meta's official API, with an owner approval gate,
duplicate protection, a content calendar and an audit trail.

What this module deliberately does **not** promise, because Meta's documentation
does not support it:

* native scheduled publishing - there is no "publish at" parameter in the
  content-publishing API, so scheduling is enforced by our own calendar;
* uploading media bytes - Meta fetches media from a URL that must be publicly
  reachable at publish time;
* publishing to personal Instagram accounts - the platform serves professional
  (business and creator) accounts;
* serving clients who have no role on the app - that needs App Review (Advanced
  Access) and a Live app, per Meta's access-level rules.

Sources for the claims above are quoted in ``docs/integrations/INSTAGRAM_SETUP.md``.

Entry points:

* ``InstagramService`` - the facade used by scripts and callers;
* ``Publisher`` - the pipeline (validate, authorise, dedupe, poll, publish);
* ``ContentCalendar`` / ``run_due`` - scheduling, dry by default;
* ``ApprovalGate`` - short-lived, content-bound owner approvals.
"""
from __future__ import annotations

from .accounts import AccountRegistry, InstagramAccount, load_registry, validate_account
from .approval import ApprovalGate, mint_approval, verify_approval
from .audit import PublishAudit, memory_audit
from .calendar import CalendarEntry, ContentCalendar
from .client import GraphClient, client_for_account
from .dedupe import PublishLedger, fingerprint
from .errors import (
    AccountDisabledError,
    AccountInvalidError,
    ApiError,
    ApprovalRequiredError,
    ConfigurationError,
    DuplicatePostError,
    InstagramError,
    PermissionDeniedError,
    PublishFailedError,
    PublishingLimitReachedError,
    RateLimitedError,
    RetryExhaustedError,
    TokenExpiredError,
    TokenUnavailableError,
    TransientError,
    UnknownAccountError,
    ValidationError,
)
from .models import (
    MAX_CAPTION_CHARS,
    MediaItem,
    Post,
    PostKind,
    PublishResult,
    validate_post,
)
from .publisher import HARD_DAILY_CAP, Publisher
from .retry import retry_call
from .scheduler import DueOutcome, run_due
from .service import InstagramService
from .tokens import TokenInfo, appsecret_proof, assert_usable, inspect_token

__all__ = [
    "MAX_CAPTION_CHARS",
    "AccountDisabledError",
    "AccountInvalidError",
    "AccountRegistry",
    "ApiError",
    "ApprovalGate",
    "ApprovalRequiredError",
    "CalendarEntry",
    "ConfigurationError",
    "ContentCalendar",
    "DueOutcome",
    "DuplicatePostError",
    "GraphClient",
    "HARD_DAILY_CAP",
    "InstagramAccount",
    "InstagramError",
    "InstagramService",
    "MediaItem",
    "PermissionDeniedError",
    "Post",
    "PostKind",
    "PublishAudit",
    "PublishFailedError",
    "PublishLedger",
    "PublishResult",
    "PublishingLimitReachedError",
    "Publisher",
    "RateLimitedError",
    "RetryExhaustedError",
    "TokenExpiredError",
    "TokenInfo",
    "TokenUnavailableError",
    "TransientError",
    "UnknownAccountError",
    "ValidationError",
    "appsecret_proof",
    "assert_usable",
    "client_for_account",
    "fingerprint",
    "inspect_token",
    "load_registry",
    "memory_audit",
    "mint_approval",
    "retry_call",
    "run_due",
    "validate_account",
    "validate_post",
    "verify_approval",
]
