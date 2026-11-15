"""Owner-only enforcement on the Telegram webhook.

The shared secret (``TELEGRAM_WEBHOOK_SECRET``) proves an update came from
Telegram; it does not prove it came from the owner. Anyone who can message the
bot produces a valid, signed update. The commands this endpoint parks
(``/approve``, ``/reject``, ``/do``) merge and deploy code, so the sender must
be an admin (``TELEGRAM_ADMIN_IDS`` / ``TELEGRAM_ADMIN_ID``). These tests drive
the real Flask route with the queues redirected to a temp dir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OWNER = 1863492058
STRANGER = 999999999
WEBHOOK_SECRET = "test-webhook-secret"


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", WEBHOOK_SECRET)
    appmod.app.config["TESTING"] = True
    c = appmod.app.test_client()
    # The webhook now fails closed without the shared secret; these tests are
    # about the admin gate, so supply a valid secret on every request.
    c.environ_base = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": WEBHOOK_SECRET}
    return c


def _msg(text, sender=OWNER, chat_id=OWNER):
    return {"message": {"text": text, "from": {"id": sender}, "chat": {"id": chat_id}}}


def _read(path):
    return json.loads(path.read_text()) if path.exists() else []


def _as_owner(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)


def test_owner_can_park_an_approval(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"))
    assert resp.status_code == 200
    assert resp.get_json()["queued"] == "command"
    assert _read(tmp_path / "commands.json")[0]["text"] == "/approve 7"


def test_stranger_cannot_park_an_approval(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", sender=STRANGER))
    assert resp.status_code == 200
    assert _read(tmp_path / "commands.json") == []


def test_stranger_cannot_park_a_work_order(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    resp = client.post("/api/telegram/webhook", json=_msg("/do rm -rf /", sender=STRANGER))
    assert resp.status_code == 200
    assert _read(tmp_path / "tasks.json") == []


def test_stranger_cannot_list_work_orders(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    resp = client.post("/api/telegram/webhook", json=_msg("/tasks", sender=STRANGER))
    assert resp.status_code == 200
    assert _read(tmp_path / "replies.json") == []


def test_stranger_button_tap_is_ignored(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    update = {"callback_query": {"id": "1", "from": {"id": STRANGER}, "data": "approve:7",
                                 "message": {"chat": {"id": STRANGER}}}}
    resp = client.post("/api/telegram/webhook", json=update)
    assert resp.status_code == 200
    assert _read(tmp_path / "commands.json") == []


def test_owner_button_tap_is_parked(client, tmp_path, monkeypatch):
    _as_owner(monkeypatch)
    update = {"callback_query": {"id": "1", "from": {"id": OWNER}, "data": "approve:7",
                                 "message": {"chat": {"id": OWNER}}}}
    resp = client.post("/api/telegram/webhook", json=update)
    assert resp.status_code == 200
    assert _read(tmp_path / "commands.json")[0]["text"] == "/approve 7"


def test_stranger_still_gets_ai_replies(client, tmp_path, monkeypatch):
    """The gate covers owner commands only; ordinary chat keeps working."""
    _as_owner(monkeypatch)
    monkeypatch.setattr("web.app._append_reply", lambda chat_id, text: None)
    resp = client.post("/api/telegram/webhook", json=_msg("/start", sender=STRANGER))
    assert resp.status_code == 200


def test_no_admin_configured_denies_owner_commands(client, tmp_path, monkeypatch):
    """No admin ids configured must deny owner commands, not stay open."""
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", sender=STRANGER))
    assert resp.status_code == 200
    assert _read(tmp_path / "commands.json") == []
    assert resp.get_json().get("queued") != "command"


def test_no_admin_configured_denies_work_orders(client, tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    client.post("/api/telegram/webhook", json=_msg("/do rm -rf /", sender=OWNER))
    assert _read(tmp_path / "tasks.json") == []


def test_no_admin_configured_denies_button_tap(client, tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    update = {"callback_query": {"id": "1", "from": {"id": OWNER}, "data": "approve:7",
                                 "message": {"chat": {"id": OWNER}}}}
    resp = client.post("/api/telegram/webhook", json=update)
    assert resp.status_code == 200
    assert _read(tmp_path / "commands.json") == []


def test_admin_id_alias_is_honoured(client, tmp_path, monkeypatch):
    monkeypatch.delenv("TELEGRAM_ADMIN_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", str(OWNER))
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 3"))
    assert resp.get_json()["queued"] == "command"


def test_multiple_admin_ids(client, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", f"{STRANGER}, {OWNER}")
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 3", sender=OWNER))
    assert resp.get_json()["queued"] == "command"
