"""Calendar, scheduler, service, demo and CLI behaviour.

The scheduler is the riskiest part of a publisher - it is the thing that acts
later without a human in the loop - so these tests focus on what it refuses to
do: publish without a per-entry approval token, publish a dry run, or leave a
failed entry looking planned.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from genesis_protocol.instagram import (
    AccountRegistry,
    ApprovalGate,
    DuplicatePostError,
    GraphClient,
    InstagramAccount,
    InstagramService,
    MediaItem,
    Post,
    PostKind,
    ValidationError,
)
from genesis_protocol.instagram.calendar import ContentCalendar
from genesis_protocol.instagram.dedupe import PublishLedger
from genesis_protocol.instagram.demo import run as run_demo
from genesis_protocol.instagram.scheduler import run_due

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
IMG = "https://cdn.example.com/a.jpg"
TOKEN = "EAAG-secret"


def account(**overrides) -> InstagramAccount:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "ig_user_id": "17841400000000001",
        "login_type": "instagram_login",
        "token_env": "IG_TOKEN_ACME",
        "token_expires_at": "2027-01-30T00:00:00Z",
    }
    base.update(overrides)
    return InstagramAccount(**base)


def post(caption="hello", **overrides) -> Post:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "kind": PostKind.IMAGE,
        "caption": caption,
        "media": (MediaItem(url=IMG),),
    }
    base.update(overrides)
    return Post(**base)


class FakeMeta:
    def __init__(self, statuses=("FINISHED",)):
        self.statuses = list(statuses)
        self.calls = []
        self.published = []

    def __call__(self, method, url, data):
        path = url.split("?")[0]
        self.calls.append((method, path, data))
        if "content_publishing_limit" in path:
            return {"data": [{"quota_usage": 0}]}
        if method == "POST" and path.endswith("/media_publish"):
            self.published.append((data or {}).get("creation_id"))
            return {"id": "178900001"}
        if method == "POST" and path.endswith("/media"):
            return {"id": "c1"}
        return {"status_code": self.statuses[0]}


def service(meta=None, *, calendar=None, ledger=None, env=None) -> InstagramService:
    meta = meta or FakeMeta()
    env = env or {"IG_TOKEN_ACME": TOKEN, "IG_APPROVAL_SECRET": "s"}
    return InstagramService(
        registry=AccountRegistry([account()]),
        ledger=ledger or PublishLedger(path=":memory:"),
        calendar=calendar or ContentCalendar(path=":memory:"),
        approvals=ApprovalGate(secret=env.get("IG_APPROVAL_SECRET", "")),
        client_factory=lambda acc: GraphClient(TOKEN, http=meta),
        env=env,
        now_fn=lambda: NOW,
        poll_interval=0.0,
        poll_timeout=1.0,
    )


# ------------------------------------------------------------ calendar


def test_calendar_add_and_due():
    cal = ContentCalendar(path=":memory:")
    entry = cal.add(post(), (NOW + timedelta(minutes=5)).isoformat(), now=NOW)
    assert entry.status == "planned"
    assert cal.due(now=NOW) == []
    assert [e.entry_id for e in cal.due(now=NOW + timedelta(minutes=10))] == [entry.entry_id]


def test_calendar_refuses_identical_planned_content():
    cal = ContentCalendar(path=":memory:")
    at = (NOW + timedelta(minutes=5)).isoformat()
    cal.add(post(), at, now=NOW)
    with pytest.raises(DuplicatePostError):
        cal.add(post(), at, now=NOW)


def test_calendar_allows_the_same_content_after_it_is_cancelled():
    cal = ContentCalendar(path=":memory:")
    at = (NOW + timedelta(minutes=5)).isoformat()
    entry = cal.add(post(), at, now=NOW)
    cal.cancel(entry.entry_id)
    again = cal.add(post(), at, now=NOW)
    assert again.status == "planned"


def test_calendar_marks_and_filters():
    cal = ContentCalendar(path=":memory:")
    at = (NOW + timedelta(minutes=5)).isoformat()
    entry = cal.add(post(), at, now=NOW)
    cal.mark(entry.entry_id, "published", post_id="p1")
    assert cal.list(status="published")[0].post_id == "p1"
    with pytest.raises(ValidationError):
        cal.cancel(entry.entry_id)  # only planned entries can be cancelled
    with pytest.raises(ValidationError):
        cal.mark(entry.entry_id, "nonsense")


def test_calendar_persists_to_disk(tmp_path):
    path = tmp_path / "cal.json"
    cal = ContentCalendar(path=path)
    entry = cal.add(post(), (NOW + timedelta(minutes=5)).isoformat(), now=NOW)
    reopened = ContentCalendar(path=path)
    assert [e.entry_id for e in reopened.list()] == [entry.entry_id]


def test_calendar_rejects_invalid_schedule_time():
    cal = ContentCalendar(path=":memory:")
    with pytest.raises(ValidationError):
        cal.add(post(), "next tuesday", now=NOW)


# ----------------------------------------------------------- scheduler


def test_due_dry_run_never_publishes():
    meta = FakeMeta()
    svc = service(meta)
    svc.schedule(post(), (NOW - timedelta(minutes=1)).isoformat())
    outcomes = run_due(svc.calendar, svc.publisher, dry_run=True, now=NOW)
    assert outcomes[0].result == "planned"
    assert meta.calls == []


def test_due_live_without_a_token_waits_for_approval():
    meta = FakeMeta()
    svc = service(meta)
    svc.schedule(post(), (NOW - timedelta(minutes=1)).isoformat())
    outcomes = run_due(svc.calendar, svc.publisher, dry_run=False, now=NOW)
    assert outcomes[0].result == "awaiting-approval"
    assert meta.calls == []
    assert svc.calendar.list(status="planned")


def test_due_live_with_a_token_publishes_and_marks_the_entry():
    meta = FakeMeta()
    svc = service(meta)
    entry = svc.schedule(post(), (NOW - timedelta(minutes=1)).isoformat())
    token = svc.mint_approval_for(entry.to_post())
    outcomes = run_due(
        svc.calendar, svc.publisher, dry_run=False, now=NOW,
        approval_tokens={entry.entry_id: token},
    )
    assert outcomes[0].result == "published"
    assert svc.calendar.list(status="published")[0].post_id == "178900001"


def test_due_marks_a_failed_entry_failed():
    meta = FakeMeta(statuses=("ERROR",))
    svc = service(meta)
    entry = svc.schedule(post(), (NOW - timedelta(minutes=1)).isoformat())
    token = svc.mint_approval_for(entry.to_post())
    outcomes = run_due(
        svc.calendar, svc.publisher, dry_run=False, now=NOW,
        approval_tokens={entry.entry_id: token},
    )
    assert outcomes[0].result == "failed"
    assert svc.calendar.list(status="failed")


# ------------------------------------------------------------- service


def test_status_never_contains_a_token_value():
    svc = service()
    payload = json.dumps(svc.status())
    assert TOKEN not in payload
    assert svc.status()["approval_configured"] is True
    assert svc.status()["accounts"][0]["token"]["present"] is True


def test_status_reports_an_unconfigured_approval_gate():
    svc = service(env={"IG_TOKEN_ACME": TOKEN})
    assert svc.status()["approval_configured"] is False


def test_service_schedule_is_audited():
    svc = service()
    svc.schedule(post(), (NOW + timedelta(hours=1)).isoformat())
    events = [e["event"] for e in svc.audit.tail(10)]
    assert "instagram.schedule.add" in events


def test_service_cancel_is_audited():
    svc = service()
    entry = svc.schedule(post(), (NOW + timedelta(hours=1)).isoformat())
    svc.cancel(entry.entry_id)
    events = [e["event"] for e in svc.audit.tail(10)]
    assert "instagram.schedule.cancel" in events


# ---------------------------------------------------------------- demo


def test_demo_runs_offline_and_reports_what_it_did():
    lines: list[str] = []
    summary = run_demo(stream=lines.append)
    rendered = "\n".join(lines) + summary["rendered_output"]
    # The demo prints no token and no app secret: not the values, not a prefix.
    for secret in ("demo-token-acme", "demo-token-bluebird", "demo-app-secret",
                   "demo-approval-secret"):
        assert secret not in rendered
    assert len(summary["published"]) == 4
    assert set(summary["blocked"]) >= {
        "ApprovalRequiredError",
        "DuplicatePostError",
        "TokenExpiredError",
        "ValidationError",
    }
    assert summary["fake_meta_published"] == 4
    assert any("instagram.publish.success" in line or "instagram.publish" in line for line in lines)


# ----------------------------------------------------------------- CLI


def test_cli_plan_and_status(tmp_path, capsys):
    from scripts.instagram import main

    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"accounts": [account().to_dict()]}), encoding="utf-8")
    base = ["--accounts-file", str(accounts),
            "--ledger-file", str(tmp_path / "ledger.json"),
            "--calendar-file", str(tmp_path / "cal.json")]

    assert main(base + ["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["accounts"][0]["account_id"] == "acme-cafe"
    assert TOKEN not in json.dumps(status)

    assert main(base + ["plan", "--account", "acme-cafe", "--client", "acme",
                        "--kind", "image", "--media", IMG, "--caption", "hi"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True


def test_cli_publish_without_approval_is_refused(tmp_path, capsys, monkeypatch):
    from scripts.instagram import main

    monkeypatch.setenv("IG_TOKEN_ACME", TOKEN)
    monkeypatch.setenv("IG_APPROVAL_SECRET", "s")
    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"accounts": [account().to_dict()]}), encoding="utf-8")
    code = main([
        "--accounts-file", str(accounts),
        "--ledger-file", str(tmp_path / "ledger.json"),
        "publish", "--account", "acme-cafe", "--client", "acme",
        "--kind", "image", "--media", IMG,
    ])
    captured = capsys.readouterr()
    assert code == 1
    assert "ApprovalRequiredError" in captured.err


def test_cli_mint_refuses_without_a_secret(tmp_path, capsys, monkeypatch):
    from scripts.instagram import main

    monkeypatch.delenv("IG_APPROVAL_SECRET", raising=False)
    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"accounts": [account().to_dict()]}), encoding="utf-8")
    code = main([
        "--accounts-file", str(accounts),
        "mint-approval", "--account", "acme-cafe", "--client", "acme",
        "--kind", "image", "--media", IMG,
    ])
    assert code == 2
    assert "IG_APPROVAL_SECRET" in capsys.readouterr().err
