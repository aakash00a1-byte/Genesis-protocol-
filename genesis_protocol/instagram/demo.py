"""Offline demo: two fake clients, a fake Meta, zero network calls.

Run it with ``python3 -m genesis_protocol.instagram.demo`` (or the CLI's
``demo`` command). It drives the real pipeline - validation, approval, dedupe,
container creation, polling, publish, calendar - against a fake HTTP layer that
imitates Meta's responses, and prints what happened at each step.

The demo is also the honest answer to "does it work?": everything it proves is
about *our* logic. It cannot prove an account's real permissions, and it never
touches the network or a real account.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .accounts import AccountRegistry, InstagramAccount
from .approval import ApprovalGate
from .audit import memory_audit
from .calendar import ContentCalendar
from .dedupe import PublishLedger
from .errors import InstagramError
from .models import MediaItem, Post, PostKind
from .service import InstagramService

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


class FakeMeta:
    """Minimal stand-in for the Instagram Graph API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.containers: dict[str, dict] = {}
        self.published: list[dict] = []
        self._next = 1

    def __call__(self, method: str, url: str, data) -> dict:
        path = url.split("?")[0]
        self.calls.append((method, path))
        if method == "POST" and path.endswith("/media_publish"):
            media_id = f"17890000{len(self.published) + 1}"
            self.published.append({"id": media_id, "creation_id": (data or {}).get("creation_id")})
            return {"id": media_id}
        if method == "POST" and path.endswith("/media"):
            container_id = f"c{self._next}"
            self._next += 1
            self.containers[container_id] = dict(data or {})
            return {"id": container_id}
        if method == "GET" and "content_publishing_limit" in path:
            return {"data": [{"quota_usage": len(self.published), "config": {"quota_total": 50}}]}
        if method == "GET" and "/c" in path:
            return {"status_code": "FINISHED", "status": "Finished"}
        return {}


def _registry() -> AccountRegistry:
    return AccountRegistry(
        [
            InstagramAccount(
                account_id="acme-cafe",
                client_id="acme",
                ig_user_id="17841400000000001",
                username="acme.cafe",
                login_type="instagram_login",
                token_env="IG_TOKEN_ACME",
                token_expires_at="2027-01-30T00:00:00Z",
            ),
            InstagramAccount(
                account_id="bluebird-bakery",
                client_id="bluebird",
                ig_user_id="17841400000000002",
                username="bluebird.bakery",
                login_type="facebook_login",
                page_id="1029384756",
                token_env="IG_TOKEN_BLUEBIRD",
                token_expires_at="2026-11-26T00:00:00Z",
            ),
            InstagramAccount(
                account_id="stale-token-client",
                client_id="stale",
                ig_user_id="17841400000000003",
                username="stale.client",
                token_env="IG_TOKEN_STALE",
                token_expires_at="2026-11-01T00:00:00Z",
            ),
        ]
    )


def run(stream=print) -> dict:
    """Execute the demo and return a machine-checkable summary."""
    env = {
        "IG_TOKEN_ACME": "demo-token-acme",
        "IG_TOKEN_BLUEBIRD": "demo-token-bluebird",
        "IG_TOKEN_STALE": "demo-token-stale",
        "IG_APP_SECRET": "demo-app-secret",
        "IG_APPROVAL_SECRET": "demo-approval-secret",
    }
    meta = FakeMeta()
    audit = memory_audit()
    ledger = PublishLedger(path=":memory:")
    calendar = ContentCalendar(path=":memory:")
    service = InstagramService(
        registry=_registry(),
        ledger=ledger,
        calendar=calendar,
        audit=audit,
        approvals=ApprovalGate(secret=env["IG_APPROVAL_SECRET"]),
        client_factory=lambda account: _client(account, env, meta),
        env=env,
        now_fn=lambda: NOW,
        poll_interval=0.0,
        poll_timeout=5.0,
        retry_attempts=2,
    )

    summary: dict = {"steps": [], "published": [], "blocked": [], "errors": []}

    def note(kind: str, text: str) -> None:
        summary["steps"].append(f"{kind}: {text}")
        stream(f"  [{kind}] {text}")

    stream("1) status - no secret values in it")
    status = service.status()
    for account in status["accounts"]:
        stream(
            f"   {account['account_id']:<20} client={account['client_id']:<9} "
            f"token_present={account['token']['present']!s:<5} "
            f"days_left={account['token']['days_left']} "
            f"expired={account['token']['expired']}"
        )
    summary["status"] = status

    image_post = Post(
        account_id="acme-cafe",
        client_id="acme",
        kind=PostKind.IMAGE,
        caption="Fresh filter coffee, brewed at 6am.",
        media=(MediaItem(url="https://cdn.example.com/acme/coffee.jpg", alt_text="A cup of coffee"),),
    )

    stream("\n2) publish without owner approval")
    try:
        service.publish(image_post)
    except InstagramError as exc:
        summary["blocked"].append(type(exc).__name__)
        note("blocked", f"{type(exc).__name__}: {exc}")

    stream("\n3) owner approves, then publish")
    token = service.mint_approval_for(image_post)
    result = service.publish(image_post, approval_token=token)
    summary["published"].append(result.post_id)
    note("published", f"{image_post.kind.value} -> post {result.post_id} (container {result.container_id})")

    stream("\n4) the same content again (duplicate protection)")
    try:
        service.publish(image_post, approval_token=service.mint_approval_for(image_post))
    except InstagramError as exc:
        summary["blocked"].append(type(exc).__name__)
        note("blocked", f"{type(exc).__name__}: {exc}")

    stream("\n5) story for the second client")
    story = Post(
        account_id="bluebird-bakery",
        client_id="bluebird",
        kind=PostKind.STORY,
        caption="ignored for stories",
        media=(MediaItem(url="https://cdn.example.com/bluebird/croissant.mp4"),),
    )
    story_result = service.publish(story, approval_token=service.mint_approval_for(story))
    summary["published"].append(story_result.post_id)
    note("published", f"story -> post {story_result.post_id}")

    stream("\n6) carousel (two children, then the carousel container)")
    carousel = Post(
        account_id="acme-cafe",
        client_id="acme",
        kind=PostKind.CAROUSEL,
        caption="Two new pastries.",
        media=(
            MediaItem(url="https://cdn.example.com/acme/a.jpg"),
            MediaItem(url="https://cdn.example.com/acme/b.jpg"),
        ),
    )
    carousel_result = service.publish(carousel, approval_token=service.mint_approval_for(carousel))
    summary["published"].append(carousel_result.post_id)
    note("published", f"carousel -> post {carousel_result.post_id}")

    stream("\n7) two refusals that protect clients")
    expired = Post(
        account_id="stale-token-client",
        client_id="stale",
        kind=PostKind.IMAGE,
        media=(MediaItem(url="https://cdn.example.com/stale/x.jpg"),),
    )
    try:
        service.publish(expired, approval_token=service.mint_approval_for(expired))
    except InstagramError as exc:
        summary["blocked"].append(type(exc).__name__)
        note("blocked", f"expired token -> {type(exc).__name__}: {exc}")

    cross = Post(
        account_id="bluebird-bakery",
        client_id="acme",  # wrong client on purpose
        kind=PostKind.IMAGE,
        media=(MediaItem(url="https://cdn.example.com/acme/z.jpg"),),
    )
    try:
        service.publish(cross, approval_token=service.mint_approval_for(cross))
    except InstagramError as exc:
        summary["blocked"].append(type(exc).__name__)
        note("blocked", f"cross-client -> {type(exc).__name__}: {exc}")

    stream("\n8) calendar: schedule, dry run, live run with and without a token")
    scheduled = Post(
        account_id="acme-cafe",
        client_id="acme",
        kind=PostKind.IMAGE,
        caption="Weekend brunch menu.",
        media=(MediaItem(url="https://cdn.example.com/acme/brunch.jpg"),),
    )
    entry = service.schedule(scheduled, (NOW + timedelta(minutes=30)).isoformat())
    later = NOW + timedelta(hours=1)
    dry = service.due(dry_run=True, now=later)
    note("calendar", f"dry run of {len(dry)} due entr(ies): {dry[0].result if dry else 'none'}")
    live_without = service.due(dry_run=False, now=later)
    note("calendar", f"live without token: {live_without[0].result if live_without else 'none'}")
    live_with = service.due(
        dry_run=False,
        now=later,
        approval_tokens={entry.entry_id: service.mint_approval_for(scheduled)},
    )
    note("calendar", f"live with token: {live_with[0].result if live_with else 'none'}")
    if live_with and live_with[0].result == "published":
        summary["published"].append(live_with[0].detail)

    stream("\n9) audit trail")
    entries = audit.tail(50)
    summary["audit_events"] = [e["event"] for e in entries]
    counts: dict[str, int] = {}
    for event in summary["audit_events"]:
        counts[event] = counts.get(event, 0) + 1
    for event, count in sorted(counts.items()):
        stream(f"   {event:<32} {count}")

    summary["network_calls"] = len(meta.calls)
    summary["fake_meta_published"] = len(meta.published)
    summary["rendered_output"] = "\n".join(summary["steps"])
    stream(
        f"\nresult: {len(summary['published'])} published, "
        f"{len(summary['blocked'])} blocked, "
        f"{len(meta.calls)} fake API calls"
    )
    return summary


def _client(account, env, meta):
    from .client import GraphClient

    return GraphClient(
        env[account.token_env],
        login_type=account.login_type,
        app_secret=env["IG_APP_SECRET"],
        http=meta,
        version="v27.0",
    )


if __name__ == "__main__":  # pragma: no cover - manual entry point
    run()
