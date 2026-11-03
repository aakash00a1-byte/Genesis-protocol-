"""Owner-ID authorization on the Telegram webhook (privileged commands).

Pinned defect: the webhook parked ``/approve``, ``/reject``, ``/do`` and
``/cancel`` from *any* chat, so any Telegram user who knew the bot could merge a
pull request or start an agent. These tests drive the real Flask routes and
assert that only the configured owner (TELEGRAM_ADMIN_IDS / TELEGRAM_ADMIN_ID)
can queue a privileged command, that a spoofed inline-button tap is ignored, and
that when no owner is configured the gate fails closed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HEADER = "X-Telegram-Bot-Api-Secret-Token"
SECRET = "s3cret"
OWNER = 1863492058
STRANGER = 999


@pytest.fixture
def appmod(tmp_path, monkeypatch):
    import web.app as module

    monkeypatch.setattr(module, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(module, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(module, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def client(appmod):
    return appmod.app.test_client()


def _msg(text, user_id):
    return {"message": {"text": text, "from": {"id": user_id}, "chat": {"id": user_id}}}


def _tap(data, user_id):
    return {
        "callback_query": {
            "data": data,
            "from": {"id": user_id},
            "message": {"chat": {"id": user_id}},
        }
    }


def _post(client, update):
    return client.post("/api/telegram/webhook", json=update, headers={HEADER: SECRET})


def test_non_owner_approve_is_dropped(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _msg("/approve 1", STRANGER)).status_code == 200
    assert appmod._read_command_queue() == []


def test_owner_approve_is_queued(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _msg("/approve 1", OWNER)).status_code == 200
    queue = appmod._read_command_queue()
    assert len(queue) == 1
    assert queue[0]["text"] == "/approve 1"


def test_non_owner_do_order_is_dropped(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _msg("/do delete everything", STRANGER)).status_code == 200
    assert appmod._read_task_queue() == []


def test_owner_do_order_is_queued(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _msg("/do add a test", OWNER)).status_code == 200
    assert len(appmod._read_task_queue()) == 1


def test_non_owner_callback_tap_is_dropped(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _tap("approve:1", STRANGER)).status_code == 200
    assert appmod._read_command_queue() == []


def test_owner_callback_tap_is_queued(client, appmod, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _tap("approve:1", OWNER)).status_code == 200
    queue = appmod._read_command_queue()
    assert len(queue) == 1
    assert queue[0]["text"] == "/approve 1"


def test_owner_id_env_var_also_authorizes(client, appmod, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", str(OWNER))
    assert _post(client, _msg("/approve 1", OWNER)).status_code == 200
    assert len(appmod._read_command_queue()) == 1


def test_fails_closed_when_no_owner_configured(client, appmod, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    assert _post(client, _msg("/approve 1", OWNER)).status_code == 200
    assert appmod._read_command_queue() == []


def test_non_owner_normal_message_still_gets_reply(client, appmod, monkeypatch):
    # The owner gate must only guard privileged commands; ordinary chat stays
    # open so the bot is still usable by other users.
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    assert _post(client, _msg("/start", STRANGER)).status_code == 200
    replies = appmod._read_reply_queue()
    assert len(replies) == 1
    assert "Genesis Protocol" in replies[0]["text"]
    assert appmod._read_command_queue() == []


def test_is_owner_ignores_blank_and_whitespace(monkeypatch, appmod):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", f" {OWNER} , 111 ")
    assert appmod._is_owner(OWNER) is True
    assert appmod._is_owner(111) is True
    assert appmod._is_owner(222) is False
    assert appmod._is_owner(None) is False
    assert appmod._is_owner("") is False
