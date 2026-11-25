"""Audit trail for publishing decisions.

This wraps the project's single audit sink (``agentic.audit.AuditLog``) instead
of starting a second log format, so an operator has one place to look and one
redaction rule to trust.

What is recorded: the decision (allowed/refused), why, the account, the client,
the content fingerprint and the Meta post id. What is *not* recorded: captions,
media URLs, tokens or app secrets. The fingerprint proves which content was
published without copying a client's text into a log file.
"""
from __future__ import annotations

from typing import Any

from ..agentic.audit import AuditLog, get_audit_log

TOOL_NAME = "instagram.publish"

ALLOWED_EVENTS = frozenset(
    {
        "instagram.plan",
        "instagram.publish.blocked",
        "instagram.publish.attempt",
        "instagram.publish.success",
        "instagram.publish.failure",
        "instagram.schedule.add",
        "instagram.schedule.cancel",
        "instagram.token.check",
        "instagram.account.check",
    }
)


class PublishAudit:
    """Small typed face over ``AuditLog`` for publishing events."""

    def __init__(self, log: AuditLog | None = None):
        self._log = log or get_audit_log()

    def record(
        self,
        event: str,
        *,
        account_id: str,
        client_id: str,
        fingerprint: str = "",
        post_id: str = "",
        container_id: str = "",
        allowed: bool | None = None,
        reason: str = "",
        extra: dict[str, Any] | None = None,
    ) -> dict:
        if event not in ALLOWED_EVENTS:
            raise ValueError(f"unknown audit event {event!r}")
        detail: dict[str, Any] = {
            "account_id": account_id,
            "client_id": client_id,
        }
        if fingerprint:
            detail["fingerprint"] = fingerprint
        if post_id:
            detail["post_id"] = post_id
        if container_id:
            detail["container_id"] = container_id
        if extra:
            # Only scalar, non-secret facts; never captions or URLs.
            for key, value in extra.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    detail[key] = value
        return self._log.record(
            event=event,
            tool=TOOL_NAME,
            allowed=allowed,
            reason=reason,
            detail=detail,
        )

    def tail(self, limit: int = 50) -> list:
        return self._log.tail(limit)


def memory_audit() -> PublishAudit:
    """An in-process audit sink, for tests and the demo."""
    return PublishAudit(AuditLog(path=":memory:"))
