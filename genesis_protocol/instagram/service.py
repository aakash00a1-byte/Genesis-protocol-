"""Facade that wires the pieces together for callers and the CLI.

A caller should not have to know how tokens, ledgers, approvals and the record
client fit together. It asks the service for ``status``, ``plan``, ``publish``,
``schedule`` or ``due``, and gets a typed result or a typed failure.

The service is deliberately not a daemon: nothing here starts a timer, a
thread or a scheduler. Running a calendar is an explicit call, so a deployed
process cannot start posting on its own.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from .accounts import AccountRegistry, InstagramAccount, load_registry
from .approval import ApprovalGate
from .audit import PublishAudit, memory_audit
from .calendar import ContentCalendar
from .client import GraphClient, client_for_account
from .dedupe import PublishLedger
from .dedupe import fingerprint as fingerprint_of
from .models import Post, PublishResult
from .publisher import Publisher
from .scheduler import DueOutcome, run_due
from .tokens import inspect_token

ClientFactory = Callable[[InstagramAccount], GraphClient]


class InstagramService:
    """One object to drive the module from Python, a CLI or a web route."""

    def __init__(
        self,
        *,
        registry: AccountRegistry | None = None,
        ledger: PublishLedger | None = None,
        calendar: ContentCalendar | None = None,
        audit: PublishAudit | None = None,
        approvals: ApprovalGate | None = None,
        client_factory: ClientFactory | None = None,
        env: Mapping[str, str] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        poll_interval: float = 60.0,
        poll_timeout: float = 300.0,
        retry_attempts: int = 3,
    ):
        self.env = dict(env) if env is not None else dict(os.environ)
        self.registry = registry if registry is not None else load_registry()
        self.ledger = ledger or PublishLedger()
        self.calendar = calendar or ContentCalendar()
        self.audit = audit or memory_audit()
        self.approvals = approvals or ApprovalGate.from_env(self.env)
        factory = client_factory or (
            lambda account: client_for_account(account, env=self.env)
        )
        self.publisher = Publisher(
            self.registry,
            ledger=self.ledger,
            audit=self.audit,
            approvals=self.approvals,
            client_factory=factory,
            env=self.env,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
            retry_attempts=retry_attempts,
            now_fn=now_fn,
        )
        self._now = now_fn or (lambda: datetime.now(UTC))

    # -- status --------------------------------------------------------
    def status(self) -> dict:
        """Everything an operator needs to see, with no secret values in it."""
        moment = self._now()
        since = moment - timedelta(hours=24)
        accounts = []
        for account in self.registry:
            info = inspect_token(account, env=self.env, now=moment)
            accounts.append(
                {
                    "account_id": account.account_id,
                    "client_id": account.client_id,
                    "username": account.username,
                    "login_type": account.login_type,
                    "enabled": account.enabled,
                    "daily_cap": min(account.daily_cap, 25),
                    "stories_supported": account.stories_supported,
                    "token": info.to_dict(),
                    "published_24h": self.ledger.count_since(account.account_id, since),
                }
            )
        return {
            "accounts": accounts,
            "clients": self.registry.clients(),
            "approval_configured": self.approvals.configured,
            "calendar": {
                "planned": len(self.calendar.list(status="planned")),
                "published": len(self.calendar.list(status="published")),
                "failed": len(self.calendar.list(status="failed")),
            },
            "published_total": self.ledger.snapshot()["published"],
        }

    # -- actions -------------------------------------------------------
    def plan(self, post: Post) -> PublishResult:
        return self.publisher.plan(post)

    def publish(self, post: Post, *, approval_token: str = "", dry_run: bool = False) -> PublishResult:
        return self.publisher.publish(post, approval_token=approval_token, dry_run=dry_run)

    def schedule(self, post: Post, scheduled_at: str):
        entry = self.calendar.add(post, scheduled_at, now=self._now())
        self.audit.record(
            "instagram.schedule.add",
            account_id=post.account_id,
            client_id=post.client_id,
            fingerprint=entry.fingerprint,
            allowed=True,
            reason=f"scheduled for {scheduled_at}",
            extra={"entry_id": entry.entry_id},
        )
        return entry

    def cancel(self, entry_id: str):
        entry = self.calendar.cancel(entry_id)
        self.audit.record(
            "instagram.schedule.cancel",
            account_id=entry.account_id,
            client_id=entry.client_id,
            fingerprint=entry.fingerprint,
            allowed=True,
            reason="cancelled",
            extra={"entry_id": entry.entry_id},
        )
        return entry

    def due(
        self,
        *,
        dry_run: bool = True,
        approval_tokens: dict[str, str] | None = None,
        now: datetime | None = None,
    ) -> list[DueOutcome]:
        return run_due(
            self.calendar,
            self.publisher,
            approval_tokens=approval_tokens,
            dry_run=dry_run,
            now=now or self._now(),
        )

    def mint_approval_for(self, post: Post, *, now: float | None = None) -> str:
        """Mint an owner approval token bound to this exact post.

        Only the holder of the approval secret can call this; the token expires
        and cannot be replayed for other content or another account.
        """
        return self.approvals.mint(post.account_id, fingerprint_of(post), now=now)
