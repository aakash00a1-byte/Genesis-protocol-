"""Publish pipeline tests, driven entirely by a fake Meta Graph API.

Each test states the failure it prevents: a duplicate public post, an
unapproved publish, a cross-client publish, a retry storm, an orphan container,
or a silent success that never happened.
"""
from __future__ import annotations

import json
import socket
from datetime import UTC, datetime, timedelta

import pytest

from genesis_protocol.instagram import (
    AccountDisabledError,
    AccountRegistry,
    ApprovalGate,
    ApprovalRequiredError,
    DuplicatePostError,
    GraphClient,
    InstagramAccount,
    MediaItem,
    Post,
    PostKind,
    Publisher,
    PublishFailedError,
    PublishingLimitReachedError,
    RateLimitedError,
    RetryExhaustedError,
    TokenExpiredError,
    ValidationError,
    memory_audit,
)
from genesis_protocol.instagram.dedupe import PublishLedger

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
TOKEN = "EAAG-super-secret-token"
IMG = "https://cdn.example.com/a.jpg"
IMG2 = "https://cdn.example.com/b.jpg"
VID = "https://cdn.example.com/a.mp4"
SECRET = "approval-secret"


class FakeMeta:
    """Records calls and replays configured responses."""

    def __init__(
        self,
        *,
        statuses=("FINISHED",),
        media_errors=(),
        publish_errors=(),
        quota=None,
        publish_id="178900001",
    ):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.statuses = list(statuses)
        self.media_errors = list(media_errors)
        self.publish_errors = list(publish_errors)
        self.quota = quota
        self.publish_id = publish_id
        self.published: list[str] = []
        self._containers = 0

    # -- helpers -------------------------------------------------------
    def paths(self, suffix: str) -> list[str]:
        return [url.split("?")[0] for method, url, _ in self.calls if url.split("?")[0].endswith(suffix)]

    def media_posts(self) -> list[dict]:
        return [data for _, url, data in self.calls if url.split("?")[0].endswith("/media")]

    def __call__(self, method: str, url: str, data):
        self.calls.append((method, url, data))
        path = url.split("?")[0]
        if "content_publishing_limit" in path:
            return self.quota if self.quota is not None else {"data": [{"quota_usage": 0}]}
        if method == "POST" and path.endswith("/media_publish"):
            if self.publish_errors:
                return self.publish_errors.pop(0)
            self.published.append((data or {}).get("creation_id", ""))
            return {"id": self.publish_id}
        if method == "POST" and path.endswith("/media"):
            if self.media_errors:
                return self.media_errors.pop(0)
            self._containers += 1
            return {"id": f"c{self._containers}"}
        if method == "GET" and not path.endswith("/media"):
            status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
            return {"status_code": status, "status": status}
        return {}


def account(**overrides) -> InstagramAccount:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "ig_user_id": "17841400000000001",
        "login_type": "instagram_login",
        "token_env": "IG_TOKEN_ACME",
        "token_expires_at": "2027-01-30T00:00:00Z",
        "daily_cap": 25,
    }
    base.update(overrides)
    return InstagramAccount(**base)


def post(kind=PostKind.IMAGE, media=(IMG,), caption="hello", **overrides) -> Post:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "kind": kind,
        "caption": caption,
        "media": tuple(MediaItem(url=url) for url in media),
    }
    base.update(overrides)
    return Post(**base)


def make_publisher(meta: FakeMeta, *, accounts=None, ledger=None, audit=None, sleeps=None, **kwargs):
    registry = AccountRegistry(accounts or [account()])
    sleeps = sleeps if sleeps is not None else []

    def factory(acc):
        return GraphClient(
            TOKEN, login_type=acc.login_type, app_secret="", http=meta, version="v27.0"
        )

    return Publisher(
        registry,
        ledger=ledger or PublishLedger(path=":memory:"),
        audit=audit or memory_audit(),
        approvals=ApprovalGate(secret=SECRET),
        client_factory=factory,
        env={"IG_TOKEN_ACME": TOKEN},
        poll_interval=0.0,
        poll_timeout=kwargs.pop("poll_timeout", 300.0),
        sleep=lambda seconds: sleeps.append(seconds),
        retry_attempts=kwargs.pop("retry_attempts", 3),
        retry_base_delay=0.0,
        now_fn=lambda: NOW,
        **kwargs,
    )


def approved(publisher: Publisher, the_post: Post) -> str:
    return publisher.approvals.mint(the_post.account_id, _fingerprint(the_post))


def _fingerprint(the_post: Post) -> str:
    from genesis_protocol.instagram import fingerprint

    return fingerprint(the_post)


# --------------------------------------------------------- happy paths


def test_image_publish_creates_a_container_then_publishes():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post()
    result = publisher.publish(the_post, approval_token=approved(publisher, the_post))

    assert result.post_id == "178900001"
    assert result.container_id == "c1"
    assert result.dry_run is False
    assert len(meta.media_posts()) == 1
    assert meta.media_posts()[0]["image_url"] == IMG
    assert meta.media_posts()[0]["caption"] == "hello"
    assert meta.published == ["c1"]


def test_story_publish_uses_stories_type_and_drops_the_caption():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post(kind=PostKind.STORY, media=(VID,), caption="ignored")
    publisher.publish(the_post, approval_token=approved(publisher, the_post))

    params = meta.media_posts()[0]
    assert params["media_type"] == "STORIES"
    assert params["video_url"] == VID
    assert "caption" not in params


def test_reel_publish_uses_reels_type():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post(kind=PostKind.REEL, media=(VID,), caption="reel it")
    publisher.publish(the_post, approval_token=approved(publisher, the_post))

    params = meta.media_posts()[0]
    assert params["media_type"] == "REELS"
    assert params["video_url"] == VID
    assert params["caption"] == "reel it"


def test_carousel_creates_children_then_the_carousel_container():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post(kind=PostKind.CAROUSEL, media=(IMG, IMG2), caption="two")
    publisher.publish(the_post, approval_token=approved(publisher, the_post))

    posts = meta.media_posts()
    assert len(posts) == 3
    assert posts[0]["is_carousel_item"] == "true"
    assert posts[1]["is_carousel_item"] == "true"
    assert posts[2]["media_type"] == "CAROUSEL"
    assert posts[2]["children"] == "c1,c2"
    assert posts[2]["caption"] == "two"
    assert meta.published == ["c3"]


def test_image_alt_text_is_forwarded():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = Post(
        account_id="acme-cafe",
        client_id="acme",
        kind=PostKind.IMAGE,
        caption="x",
        media=(MediaItem(url=IMG, alt_text="a cup of coffee"),),
    )
    publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert meta.media_posts()[0]["alt_text"] == "a cup of coffee"


# ------------------------------------------------------------- polling


def test_container_is_polled_until_finished():
    meta = FakeMeta(statuses=("IN_PROGRESS", "IN_PROGRESS", "FINISHED"))
    sleeps: list[float] = []
    publisher = make_publisher(meta, sleeps=sleeps)
    the_post = post()
    publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert len(sleeps) == 2


def test_error_status_publishes_nothing():
    meta = FakeMeta(statuses=("ERROR",))
    publisher = make_publisher(meta)
    the_post = post()
    with pytest.raises(PublishFailedError, match="ERROR"):
        publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert meta.published == []


def test_unfinished_container_is_never_published():
    meta = FakeMeta(statuses=("IN_PROGRESS",))
    publisher = make_publisher(meta, poll_timeout=0.0)
    the_post = post()
    with pytest.raises(PublishFailedError, match="not publishing"):
        publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert meta.published == []


# --------------------------------------------------------------- retries


def test_transient_media_failure_is_retried_then_succeeds():
    meta = FakeMeta(media_errors=[{"error": {"message": "try later", "code": 1}}])
    publisher = make_publisher(meta)
    the_post = post()
    result = publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert result.post_id == "178900001"
    assert len(meta.media_posts()) == 2


def test_validation_error_is_not_retried():
    meta = FakeMeta(media_errors=[{"error": {"message": "bad image", "code": 100}}])
    publisher = make_publisher(meta)
    the_post = post()
    with pytest.raises(ValidationError):
        publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert len(meta.media_posts()) == 1


def test_rate_limit_is_retried_then_gives_up():
    meta = FakeMeta(media_errors=[{"error": {"message": "slow down", "code": 4}}] * 3)
    publisher = make_publisher(meta, retry_attempts=3)
    the_post = post()
    with pytest.raises((RateLimitedError, RetryExhaustedError)):
        publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert len(meta.media_posts()) == 3  # retry_attempts=3 means three calls in total


# ------------------------------------------------------ refusal ordering


def test_publishing_without_approval_makes_no_api_call():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    with pytest.raises(ApprovalRequiredError):
        publisher.publish(post())
    assert meta.calls == []


def test_approval_for_other_content_is_refused():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    other = post(caption="different")
    token = publisher.approvals.mint("acme-cafe", _fingerprint(other))
    with pytest.raises(ApprovalRequiredError):
        publisher.publish(post(), approval_token=token)
    assert meta.calls == []


def test_expired_token_blocks_before_any_call():
    meta = FakeMeta()
    expired = account(token_expires_at="2026-11-01T00:00:00Z")
    publisher = make_publisher(meta, accounts=[expired])
    with pytest.raises(TokenExpiredError):
        publisher.publish(post(), approval_token="v1.9999999999.abc")
    assert meta.calls == []


def test_cross_client_publish_is_refused():
    meta = FakeMeta()
    registry = AccountRegistry(
        [account(), account(account_id="bluebird", client_id="bluebird", ig_user_id="17841400000000002")]
    )
    publisher = Publisher(
        registry,
        ledger=PublishLedger(path=":memory:"),
        audit=memory_audit(),
        approvals=ApprovalGate(secret=SECRET),
        client_factory=lambda acc: GraphClient(TOKEN, http=meta),
        env={"IG_TOKEN_ACME": TOKEN},
        poll_interval=0.0,
        sleep=lambda _s: None,
    )
    bad = Post(account_id="bluebird", client_id="acme", kind=PostKind.IMAGE,
               caption="x", media=(MediaItem(url=IMG),))
    with pytest.raises(ValidationError, match="another client's account"):
        publisher.publish(bad, approval_token=SECRET and publisher.approvals.mint(
            "bluebird", _fingerprint(bad)))
    assert meta.calls == []


def test_disabled_account_is_refused():
    meta = FakeMeta()
    publisher = make_publisher(meta, accounts=[account(enabled=False)])
    with pytest.raises(AccountDisabledError):
        publisher.publish(post(), approval_token="v1.1.abc")
    assert meta.calls == []


def test_duplicate_content_is_refused_and_not_sent_twice():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post()
    publisher.publish(the_post, approval_token=approved(publisher, the_post))
    calls_after_first = len(meta.calls)

    with pytest.raises(DuplicatePostError):
        publisher.publish(post(), approval_token=approved(publisher, post()))
    assert len(meta.calls) == calls_after_first


def test_daily_cap_is_enforced_locally():
    ledger = PublishLedger(path=":memory:")
    meta = FakeMeta()
    publisher = make_publisher(meta, accounts=[account(daily_cap=1)], ledger=ledger)
    first = post()
    publisher.publish(first, approval_token=approved(publisher, first))

    second = post(caption="a different post")
    with pytest.raises(PublishingLimitReachedError):
        publisher.publish(second, approval_token=approved(publisher, second))


def test_dry_run_never_touches_the_network():
    meta = FakeMeta()
    publisher = make_publisher(meta)
    result = publisher.publish(post(), dry_run=True)
    assert result.dry_run is True
    assert meta.calls == []


# --------------------------------------------------------------- audit


def test_audit_records_the_decision_without_content_or_secrets():
    audit = memory_audit()
    meta = FakeMeta()
    publisher = make_publisher(meta, audit=audit)
    the_post = post(caption="secret recipe for croissants")
    publisher.publish(the_post, approval_token=approved(publisher, the_post))

    entries = audit.tail(20)
    events = [e["event"] for e in entries]
    assert "instagram.publish.attempt" in events
    assert "instagram.publish.success" in events
    blob = json.dumps(entries)
    assert "secret recipe" not in blob
    assert TOKEN not in blob
    assert IMG not in blob  # media URLs are not logged either


def test_blocked_publish_is_audited():
    audit = memory_audit()
    publisher = make_publisher(FakeMeta(), audit=audit)
    with pytest.raises(ApprovalRequiredError):
        publisher.publish(post())
    assert any(e["event"] == "instagram.publish.blocked" for e in audit.tail(10))


def test_failed_publish_is_audited_with_the_reason():
    audit = memory_audit()
    meta = FakeMeta(statuses=("ERROR",))
    publisher = make_publisher(meta, audit=audit)
    the_post = post()
    with pytest.raises(PublishFailedError):
        publisher.publish(the_post, approval_token=approved(publisher, the_post))
    failures = [e for e in audit.tail(10) if e["event"] == "instagram.publish.failure"]
    assert failures and "PublishFailedError" in failures[-1]["reason"]


def test_publishing_limit_usage_is_recorded_for_observability():
    audit = memory_audit()
    meta = FakeMeta(quota={"data": [{"quota_usage": 12, "config": {"quota_total": 50}}]})
    publisher = make_publisher(meta, audit=audit)
    the_post = post()
    publisher.publish(the_post, approval_token=approved(publisher, the_post))
    attempt = [e for e in audit.tail(10) if e["event"] == "instagram.publish.attempt"][-1]
    assert "meta_quota_usage" in attempt["detail"]


# ------------------------------------------------------------- realism


def test_whole_publish_runs_with_sockets_disabled(monkeypatch):
    """The pipeline must be testable with zero network access."""

    class NoSocket:
        def __init__(self, *a, **k):
            raise AssertionError("a real socket was opened during a mocked publish")

    monkeypatch.setattr(socket, "socket", NoSocket)
    meta = FakeMeta()
    publisher = make_publisher(meta)
    the_post = post()
    result = publisher.publish(the_post, approval_token=approved(publisher, the_post))
    assert result.post_id == "178900001"


def test_ledger_persists_across_instances(tmp_path):
    ledger_path = tmp_path / "ledger.json"
    ledger = PublishLedger(path=ledger_path)
    meta = FakeMeta()
    publisher = make_publisher(meta, ledger=ledger)
    the_post = post()
    publisher.publish(the_post, approval_token=approved(publisher, the_post))

    reopened = PublishLedger(path=ledger_path)
    assert reopened.is_duplicate(the_post, now=NOW)


def test_ledger_window_expires():
    ledger = PublishLedger(path=":memory:")
    meta = FakeMeta()
    publisher = make_publisher(meta, ledger=ledger)
    the_post = post()
    publisher.publish(the_post, approval_token=approved(publisher, the_post))
    later = NOW + timedelta(hours=25)
    assert ledger.is_duplicate(the_post, now=later) == ""
