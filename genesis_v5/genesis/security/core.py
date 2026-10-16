"""Genesis Security Core.

Binds authentication boundary, authorization, role/capability permissions,
secret redaction, audit logging, structured events, rate limiting, input/
output validation, and provider/agent/tool isolation into one zero-trust
chokepoint.

No model, agent, tool, or provider gets implicit authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from genesis.core import AuditEvent
from genesis.exceptions import PermissionDenied, RateLimitExceeded, ValidationError
from genesis.security.audit import AuditLogger
from genesis.security.permissions import Permission, PolicyEngine, Role, RoleCatalog
from genesis.security.ratelimit import RateLimiter
from genesis.security.redaction import Redactor
from genesis.security.validation import (
    InputValidator,
    OutputValidator,
    ValidationResult,
)

if TYPE_CHECKING:
    # Type-only: importing ErrorTracker at runtime here would create a cycle
    # (security -> monitoring -> security.redaction). The runtime import is
    # deferred inside SecurityCore.__init__.
    from genesis.monitoring.errors import ErrorTracker


@dataclass
class Principal:
    """Authenticated caller identity."""

    actor: str
    role: str = "none"
    is_model: bool = False
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "role": self.role,
            "is_model": self.is_model,
            "metadata": dict(self.metadata or {}),
        }


@dataclass
class SecureCall:
    """A permitted, audited operation (the result of authorize)."""

    granted: bool
    principal: Principal
    permission: Permission
    audit_event: Any = None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.granted


class SecurityCore:
    """Zero-trust chokepoint for all Kernel-adjacent operations."""

    def __init__(
        self,
        *,
        audit: AuditLogger | None = None,
        policy: PolicyEngine | None = None,
        limiter: RateLimiter | None = None,
        input_validator: InputValidator | None = None,
        output_validator: OutputValidator | None = None,
        error_tracker: ErrorTracker | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.audit = audit or AuditLogger()
        self.policy = policy or PolicyEngine(RoleCatalog)
        self._limiter = limiter or RateLimiter(limit_per_minute=120)
        self._input = input_validator or InputValidator()
        self._output = output_validator or OutputValidator()
        if error_tracker is None:
            from genesis.monitoring.errors import ErrorTracker  # defer to avoid cycle

            error_tracker = ErrorTracker()
        self.errors = error_tracker
        self.redactor = redactor or Redactor()

    # ------------------------------------------------------------------
    # Authentication boundary
    # ------------------------------------------------------------------
    def authenticate(self, actor: str, role: str = "none", *, is_model: bool = False) -> Principal:
        """The authentication boundary: unknown actors get the zero-trust
        role (granting nothing)."""
        role = role if self.policy.has_role(role) else "none"
        return Principal(actor=actor, role=role, is_model=is_model)

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------
    def check_rate_limit(self, key: str) -> None:
        if not self._limiter.allow(key):
            raise RateLimitExceeded(f"rate limit exceeded for {key!r}")

    def rate_limiter(self) -> RateLimiter:
        return self._limiter

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------
    def authorize(
        self,
        principal: Principal,
        permission: Permission,
        *,
        resource: str = "",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Authorize an operation against the principal's role and audit it.

        Raises PermissionDenied when not explicitly granted.
        """
        if not self.policy.allows_role(principal.role, permission):
            event = self.audit.record(
                event_type="authz_denied",
                actor=principal.actor,
                action=f"{permission.value}:{resource}",
                resource=resource,
                status="denied",
                risk_level="critical" if not principal.is_model else "high",
                details={
                    **dict(details or {}),
                    "role": principal.role,
                    "is_model": principal.is_model,
                },
            )
            raise PermissionDenied(
                f"{principal.actor!r} (role {principal.role!r}) lacks {permission.value}"
            )
        return self.audit.record(
            event_type="authz_granted",
            actor=principal.actor,
            action=f"{permission.value}:{resource}",
            resource=resource,
            status="granted",
            details={
                **dict(details or {}),
                "role": principal.role,
                "is_model": principal.is_model,
            },
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validate_input(self, **kwargs: Any) -> None:
        result = self._input.validate_tool_request(kwargs["tool_name"], kwargs["args"])
        if not result.ok:
            raise ValidationError("; ".join(result.errors))

    def validate_output(self, output: Any) -> None:
        result = self._output.validate_output(output)
        if not result.ok:
            raise ValidationError("; ".join(result.errors))

    def output_contains_secret(self, output: Any) -> bool:
        return self._output.contains_secret(output)

    def contains_injection_markers(self, text: str) -> bool:
        return self._input.contains_injection_markers(text)

    # ------------------------------------------------------------------
    # Error tracking
    # ------------------------------------------------------------------
    def track_error(
        self,
        *,
        kind: str,
        message: str,
        component: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.errors.record(
            kind=kind, message=message, component=component, details=details
        )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "roles": sorted(self.policy.roles()),
            "rate_limit_per_minute": self._limiter.limit,
            "errors_tracked": self.errors.count(),
            "audit_events": self.audit.count(),
        }