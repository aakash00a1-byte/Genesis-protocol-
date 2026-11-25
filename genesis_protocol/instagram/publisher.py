"""The publish pipeline: validate, authorise, de-duplicate, poll, publish.

Order matters and is deliberate. Everything cheap and decisive runs before any
network call, and everything that could put content in front of the public runs
only after the owner's approval has been verified. A refusal therefore costs
nothing and leaves no orphan container behind.

Meta's flow is two steps and we follow it exactly: create a media container,
poll its ``status_code`` until it is ``FINISHED``, then call
``media_publish``. Meta's own guidance is to poll once per minute for no more
than five minutes, which is the default here.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from .accounts import AccountRegistry, InstagramAccount
from .approval import ApprovalGate
from .audit import PublishAudit, memory_audit
from .client import GraphClient, client_for_account
from .dedupe import PublishLedger, fingerprint
from .errors import (
    AccountDisabledError,
    ApprovalRequiredError,
    DuplicatePostError,
    InstagramError,
    PublishFailedError,
    PublishingLimitReachedError,
    RetryExhaustedError,
    ValidationError,
)
from .models import MEDIA_TYPE_BY_KIND, MediaItem, Post, PostKind, PublishResult, validate_post
from .retry import retry_call
from .tokens import assert_usable, inspect_token

# Our own ceiling, independent of Meta's. Meta's content-publishing guide gives
# two different figures for a rolling 24-hour window (100 API-published posts
# in the rate-limit section, 50 in the carousel limitations section), so we stay
# far below both and make the number explicit per account.
HARD_DAILY_CAP = 25

TERMINAL_OK = "FINISHED"
TERMINAL_BAD = {"ERROR", "EXPIRED"}


class Publisher:
    """Publishes one post at a time, for one named account."""

    def __init__(
        self,
        registry: AccountRegistry,
        *,
        ledger: PublishLedger | None = None,
        audit: PublishAudit | None = None,
        approvals: ApprovalGate | None = None,
        client_factory: Callable[[InstagramAccount], GraphClient] | None = None,
        env: Mapping[str, str] | None = None,
        poll_interval: float = 60.0,
        poll_timeout: float = 300.0,
        sleep: Callable[[float], None] = time.sleep,
        retry_attempts: int = 3,
        retry_base_delay: float = 0.5,
        now_fn: Callable[[], datetime] | None = None,
    ):
        self.registry = registry
        self.ledger = ledger or PublishLedger()
        self.audit = audit or memory_audit()
        self.approvals = approvals or ApprovalGate.from_env()
        self._client_factory = client_factory or client_for_account
        self._env = env
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._sleep = sleep
        self.retry_attempts = retry_attempts
        self.retry_base_delay = retry_base_delay
        self._now = now_fn or (lambda: datetime.now(UTC))

    # -- helpers -------------------------------------------------------
    def _client(self, account: InstagramAccount) -> GraphClient:
        return self._client_factory(account)

    def _daily_cap(self, account: InstagramAccount) -> int:
        return max(0, min(account.daily_cap, HARD_DAILY_CAP))

    def _check_quota(self, account: InstagramAccount, moment: datetime) -> int:
        cap = self._daily_cap(account)
        used = self.ledger.count_since(account.account_id, moment - timedelta(hours=24))
        if used >= cap:
            raise PublishingLimitReachedError(
                f"account {account.account_id!r} already published {used} post(s) in "
                f"the last 24h; the configured cap is {cap}"
            )
        return used

    def _container_params(self, post: Post) -> dict[str, str]:
        params: dict[str, str] = {}
        item = post.media[0]
        if post.kind is PostKind.IMAGE:
            params["image_url"] = item.url
            if post.caption:
                params["caption"] = post.caption
            if item.alt_text:
                params["alt_text"] = item.alt_text
        elif post.kind in (PostKind.VIDEO, PostKind.REEL):
            params["media_type"] = MEDIA_TYPE_BY_KIND[post.kind]
            params["video_url"] = item.url
            if post.caption:
                params["caption"] = post.caption
        elif post.kind is PostKind.STORY:
            params["media_type"] = MEDIA_TYPE_BY_KIND[post.kind]
            params["video_url" if item.is_video() else "image_url"] = item.url
            # Stories take no caption in Meta's publishing parameters, so the
            # caption is dropped rather than sent and rejected.
        return params

    def _carousel_child_params(self, item: MediaItem) -> dict[str, str]:
        params: dict[str, str] = {"is_carousel_item": "true"}
        if item.is_video():
            params["media_type"] = "VIDEO"
            params["video_url"] = item.url
        else:
            params["image_url"] = item.url
        if item.alt_text:
            params["alt_text"] = item.alt_text
        return params

    def _wait_for_container(self, client: GraphClient, container_id: str) -> str:
        waited = 0.0
        last = ""
        while True:
            last = client.container_status(container_id)
            if last == TERMINAL_OK:
                return last
            if last in TERMINAL_BAD:
                raise PublishFailedError(
                    f"container {container_id} ended in status {last!r}; nothing was published"
                )
            if waited >= self.poll_timeout:
                raise PublishFailedError(
                    f"container {container_id} still {last or 'unknown'!r} after "
                    f"{int(waited)}s; not publishing media Meta has not finished processing"
                )
            self._sleep(self.poll_interval)
            waited += self.poll_interval

    def _retry(self, fn):
        return retry_call(
            fn,
            attempts=self.retry_attempts,
            base_delay=self.retry_base_delay,
            max_delay=max(self.retry_base_delay * 4, 1.0),
            deadline_seconds=max(self.poll_timeout, 30.0),
            sleep=self._sleep,
        )

    # -- the pipeline --------------------------------------------------
    def plan(self, post: Post) -> PublishResult:
        """Validate and report what would happen. Never touches the network."""
        validate_post(post)
        account = self.registry.get(post.account_id)
        self._assert_same_client(account, post)
        info = inspect_token(account, env=self._env, now=self._now())
        self.audit.record(
            "instagram.plan",
            account_id=account.account_id,
            client_id=account.client_id,
            fingerprint=fingerprint(post),
            allowed=True,
            reason=f"plan for {post.kind.value}",
            extra={"token_present": info.present, "token_expired": info.expired},
        )
        return PublishResult(
            account_id=account.account_id,
            client_id=account.client_id,
            kind=post.kind,
            dry_run=True,
            steps=(
                "validate",
                "account",
                "token",
                "dedupe",
                "quota",
                "approval",
                "create-container",
                "poll-status",
                "publish",
            ),
        )

    @staticmethod
    def _assert_same_client(account: InstagramAccount, post: Post) -> None:
        if account.client_id != post.client_id:
            raise ValidationError(
                f"post is for client {post.client_id!r} but account "
                f"{account.account_id!r} belongs to {account.client_id!r}; refusing "
                "to publish one client's content to another client's account"
            )

    def publish(
        self,
        post: Post,
        *,
        approval_token: str = "",
        dry_run: bool = False,
        window_hours: int = 24,
    ) -> PublishResult:
        """Publish ``post`` or raise. ``dry_run`` stops before the first write."""
        validate_post(post)
        account = self.registry.get(post.account_id, require_enabled=False)
        self._assert_same_client(account, post)
        if not account.enabled:
            self.audit.record(
                "instagram.publish.blocked",
                account_id=account.account_id,
                client_id=account.client_id,
                allowed=False,
                reason="account disabled",
            )
            raise AccountDisabledError(f"account {account.account_id!r} is disabled")

        moment = self._now()
        assert_usable(account, env=self._env, now=moment)
        content_id = fingerprint(post)

        try:
            self.ledger.assert_not_duplicate(post, now=moment, window_hours=window_hours)
        except DuplicatePostError as exc:
            self.audit.record(
                "instagram.publish.blocked",
                account_id=account.account_id,
                client_id=account.client_id,
                fingerprint=content_id,
                allowed=False,
                reason=str(exc),
            )
            raise

        used = self._check_quota(account, moment)

        if dry_run:
            self.audit.record(
                "instagram.plan",
                account_id=account.account_id,
                client_id=account.client_id,
                fingerprint=content_id,
                allowed=True,
                reason="dry run stopped before creating a container",
                extra={"used_24h": used},
            )
            return self.plan(post)

        try:
            self.approvals.require(approval_token, account.account_id, content_id)
        except ApprovalRequiredError as exc:
            self.audit.record(
                "instagram.publish.blocked",
                account_id=account.account_id,
                client_id=account.client_id,
                fingerprint=content_id,
                allowed=False,
                reason=str(exc),
            )
            raise

        client = self._client(account)
        quota = {}
        try:
            quota = client.publishing_limit(account.ig_user_id)
        except InstagramError:
            quota = {}

        self.audit.record(
            "instagram.publish.attempt",
            account_id=account.account_id,
            client_id=account.client_id,
            fingerprint=content_id,
            allowed=True,
            reason=f"publishing {post.kind.value}",
            extra={
                "used_24h": used,
                "daily_cap": self._daily_cap(account),
                "meta_quota_usage": quota.get("quota_usage"),
            },
        )

        try:
            container_id = self._create_container(client, account, post)
            self._wait_for_container(client, container_id)
            post_id = self._retry(
                lambda: client.publish_container(account.ig_user_id, container_id)
            )
        except (InstagramError, RetryExhaustedError) as exc:
            self.audit.record(
                "instagram.publish.failure",
                account_id=account.account_id,
                client_id=account.client_id,
                fingerprint=content_id,
                allowed=False,
                reason=f"{type(exc).__name__}: {exc}",
            )
            raise

        self.ledger.record(post, post_id, now=moment)
        self.audit.record(
            "instagram.publish.success",
            account_id=account.account_id,
            client_id=account.client_id,
            fingerprint=content_id,
            post_id=post_id,
            container_id=container_id,
            allowed=True,
            reason=f"published {post.kind.value}",
        )
        return PublishResult(
            account_id=account.account_id,
            client_id=account.client_id,
            kind=post.kind,
            container_id=container_id,
            post_id=post_id,
            dry_run=False,
            steps=("validate", "account", "token", "dedupe", "quota", "approval",
                   "create-container", "poll-status", "publish"),
        )

    def _create_container(
        self, client: GraphClient, account: InstagramAccount, post: Post
    ) -> str:
        if post.kind is not PostKind.CAROUSEL:
            params = self._container_params(post)
            return self._retry(
                lambda: client.create_media_container(account.ig_user_id, params)
            )

        children: list[str] = []
        for item in post.media:
            child = self._retry(
                lambda item=item: client.create_media_container(
                    account.ig_user_id, self._carousel_child_params(item)
                )
            )
            self._wait_for_container(client, child)
            children.append(child)
        params = {"media_type": "CAROUSEL", "children": ",".join(children)}
        if post.caption:
            params["caption"] = post.caption
        return self._retry(lambda: client.create_media_container(account.ig_user_id, params))
