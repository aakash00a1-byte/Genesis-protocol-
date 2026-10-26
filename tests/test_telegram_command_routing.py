"""Telegram command routing and sender authorisation.

Two defects these tests hold fixed:

1. ``/status`` and ``/help`` were swallowed into the owner-command queue (the
   ``parse_command`` regex matches both), so the bot's own status/help replies
   were unreachable dead code. Only the harness-owned verbs may be parked now.
2. Privileged commands (``/do``, ``/cancel``, ``/tasks``, ``/approve``,
   ``/reject``, ``/list``, ``/updates``, ``/pending``, ``/status <id>``) were
   accepted from any Telegram user. They now require a configured owner id and
   fail closed when ``TELEGRAM_ADMIN_IDS`` is unset.

The routes are driven for real; only the queue paths are redirected to tmp.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OWNER_ID = 1863492058
STRANGER_ID = 999999


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    paths = {
        "TELEGRAM_REPLY_QUEUE": tmp_path / "replies.json",
        "TELEGRAM_COMMAND_QUEUE": tmp_path / "commands.json",
        "TELEGRAM_TASK_QUEUE": tmp_path / "tasks.json",
    }
    for name, path in paths.items():
        monkeypatch.setattr(appmod, name, str(path))
    # Webhook secret unset so these tests exercise routing/authorisation alone;
    # the secret contract has its own file (test_web_webhook_secret.py).
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()
    client.paths = paths
    return client


def _read(client, key):
    path = Path(client.paths[key])
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _msg(text, sender=OWNER_ID):
    return {
        "message": {
            "text": text,
            "from": {"id": sender, "first_name": "T"},
            "chat": {"id": sender, "type": "private"},
        }
    }


def _post(client, update):
    resp = client.post("/api/telegram/webhook", json=update)
    assert resp.status_code == 200, resp.data
    return resp.get_json()


# --------------------------------------------------------------------------
# /status and /help must be answered, never parked
# --------------------------------------------------------------------------
def test_status_is_answered_not_queued(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg("/status"))
    assert body.get("queued") != "command"
    assert _read(client, "TELEGRAM_COMMAND_QUEUE") == []
    replies = _read(client, "TELEGRAM_REPLY_QUEUE")
    assert len(replies) == 1
    assert "Genesis bot running" in replies[0]["text"]


def test_help_is_answered_not_queued(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg("/help"))
    assert body.get("queued") != "command"
    assert _read(client, "TELEGRAM_COMMAND_QUEUE") == []
    replies = _read(client, "TELEGRAM_REPLY_QUEUE")
    assert len(replies) == 1
    assert "/approve" in replies[0]["text"]


def test_status_with_id_is_still_parked_for_the_harness(client, monkeypatch):
    """`/status <id>` is an update lookup, so it stays harness-owned."""
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg("/status 17"))
    assert body.get("queued") == "command"
    queued = _read(client, "TELEGRAM_COMMAND_QUEUE")
    assert [c["text"] for c in queued] == ["/status 17"]


# --------------------------------------------------------------------------
# Harness-owned verbs still queue, for the owner
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text", ["/approve 1", "/reject 1", "/list", "/updates", "/pending"])
def test_owner_approval_commands_are_queued(client, monkeypatch, text):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg(text))
    assert body.get("queued") == "command"
    queued = _read(client, "TELEGRAM_COMMAND_QUEUE")
    assert [c["text"] for c in queued] == [text]


@pytest.mark.parametrize("text", ["/do add a test", "/cancel 1", "/tasks"])
def test_owner_work_orders_are_accepted(client, monkeypatch, text):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg(text))
    assert body.get("denied") is None
    if text.startswith("/do"):
        assert body.get("queued") == "work-order"
        assert len(_read(client, "TELEGRAM_TASK_QUEUE")) == 1


# --------------------------------------------------------------------------
# Unauthorised senders
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    ["/approve 1", "/reject 1", "/list", "/updates", "/pending", "/status 17"],
)
def test_stranger_cannot_queue_owner_commands(client, monkeypatch, text):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg(text, sender=STRANGER_ID))
    assert body.get("denied") == "not-owner"
    assert _read(client, "TELEGRAM_COMMAND_QUEUE") == []


def test_stranger_cannot_place_work_order(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    body = _post(client, _msg("/do delete everything", sender=STRANGER_ID))
    assert body.get("denied") == "not-owner"
    assert _read(client, "TELEGRAM_TASK_QUEUE") == []


def test_stranger_forged_callback_is_rejected(client, monkeypatch):
    """An inline Approve button tapped by a non-owner must not queue a merge."""
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    update = {
        "callback_query": {
            "id": "1",
            "data": "approve:17",
            "from": {"id": STRANGER_ID},
            "message": {"chat": {"id": STRANGER_ID}},
        }
    }
    body = _post(client, update)
    assert body.get("denied") == "not-owner"
    assert _read(client, "TELEGRAM_COMMAND_QUEUE") == []


def test_owner_callback_still_queues(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    update = {
        "callback_query": {
            "id": "1",
            "data": "approve:17",
            "from": {"id": OWNER_ID},
            "message": {"chat": {"id": OWNER_ID}},
        }
    }
    body = _post(client, update)
    assert body.get("queued") == "callback"
    assert [c["text"] for c in _read(client, "TELEGRAM_COMMAND_QUEUE")] == ["/approve 17"]


# --------------------------------------------------------------------------
# Fail closed when no owner is configured
# --------------------------------------------------------------------------
def test_unset_admin_ids_refuses_privileged_commands(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    body = _post(client, _msg("/approve 1"))
    assert body.get("denied") == "not-owner"
    assert _read(client, "TELEGRAM_COMMAND_QUEUE") == []


def test_unset_admin_ids_refuses_callback(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    update = {
        "callback_query": {
            "id": "1",
            "data": "approve:17",
            "from": {"id": OWNER_ID},
            "message": {"chat": {"id": OWNER_ID}},
        }
    }
    assert _post(client, update).get("denied") == "not-owner"


def test_missing_sender_is_refused(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER_ID))
    update = {"message": {"text": "/approve 1", "chat": {"id": OWNER_ID}}}
    assert _post(client, update).get("denied") == "not-owner"


# --------------------------------------------------------------------------
# Non-privileged traffic is unaffected
# --------------------------------------------------------------------------
def test_start_is_answered_for_anyone(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    _post(client, _msg("/start", sender=STRANGER_ID))
    replies = _read(client, "TELEGRAM_REPLY_QUEUE")
    assert any("Genesis Protocol" in r["text"] for r in replies)


def test_unknown_command_gets_a_hint(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    _post(client, _msg("/nonsense"))
    replies = _read(client, "TELEGRAM_REPLY_QUEUE")
    assert any("Unknown command" in r["text"] for r in replies)


def test_admin_ids_accepts_comma_and_semicolon(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", f"{OWNER_ID}, 42; 7")
    body = _post(client, _msg("/list", sender=42))
    assert body.get("queued") == "command"
