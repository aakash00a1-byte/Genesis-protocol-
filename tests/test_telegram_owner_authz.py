"""Owner authorization on the privileged Telegram paths.

The webhook parks owner commands (/approve, /reject, /updates) and work orders
(/do, /tasks, /cancel) for the self-improvement harness, which merges the PR and
triggers the deploy. Before this fix the sender was never checked, so anyone who
knew the bot's public username could queue an /approve.

These tests drive the real Flask route with the queue files redirected to a temp
dir, and hold the contract that only the verified sender id from the update —
never a value in the message text or button payload — can authorise a privileged
command. No GitHub or deployment API is ever called; the harness tests use a
fake transport.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OWNER = "1863492058"
STRANGER = "999999999"
HEADER = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Every test starts from "nothing configured" so behaviour cannot depend on
    # the ambient environment.
    for name in ("GENESIS_ENV", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_ADMIN_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def appmod():
    import web.app as module

    return module


@pytest.fixture
def client(appmod, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _msg(text, from_id=OWNER, chat_id=OWNER):
    message = {"text": text, "chat": {"id": chat_id}}
    if from_id is not None:
        message["from"] = {"id": from_id}
    return {"message": message}


def _callback(data, from_id=OWNER, chat_id=OWNER):
    callback = {"id": "cb1", "data": data, "message": {"chat": {"id": chat_id}}}
    if from_id is not None:
        callback["from"] = {"id": from_id}
    return {"callback_query": callback}


def _commands(tmp_path):
    path = tmp_path / "commands.json"
    return json.loads(path.read_text()) if path.exists() else []


# ---------------------------------------------------------------------------
# Typed commands
# ---------------------------------------------------------------------------
def test_owner_approve_is_queued(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"))
    assert resp.status_code == 200
    assert resp.get_json()["queued"] == "command"
    commands = _commands(tmp_path)
    assert len(commands) == 1
    assert commands[0]["text"] == "/approve 7"
    # The verified sender is recorded so the harness can re-check it.
    assert str(commands[0]["from_id"]) == OWNER


def test_owner_reject_is_queued(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/reject 3 why not"))
    assert resp.get_json()["queued"] == "command"
    assert _commands(tmp_path)[0]["text"] == "/reject 3 why not"


def test_stranger_approve_is_denied_and_not_queued(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", from_id=STRANGER))
    assert resp.status_code == 200
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_stranger_reject_is_denied_and_not_queued(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/reject 3", from_id=STRANGER))
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_missing_sender_identity_is_denied(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", from_id=None))
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_no_owner_configured_denies_everyone(client, appmod, tmp_path, monkeypatch):
    # Fail closed: with TELEGRAM_ADMIN_ID unset nobody is an owner.
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", from_id=OWNER))
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_forged_owner_id_in_message_text_does_not_authorize(client, appmod, tmp_path, monkeypatch):
    # A stranger who knows the owner id and types it into the message gains
    # nothing: only the verified sender id is consulted.
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post(
        "/api/telegram/webhook",
        json=_msg(f"/approve 7 {OWNER} owner={OWNER}", from_id=STRANGER),
    )
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_non_privileged_message_still_works_for_stranger(client, appmod, tmp_path, monkeypatch):
    # Authorization must not break ordinary use of the bot.
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/start", from_id=STRANGER))
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert _commands(tmp_path) == []


# ---------------------------------------------------------------------------
# Work orders (also privileged: they spawn an agent run that opens a PR)
# ---------------------------------------------------------------------------
def test_stranger_work_order_is_denied(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/do fix the bug", from_id=STRANGER))
    assert resp.get_json()["denied"] == "not-owner"
    assert not (tmp_path / "tasks.json").exists()


# ---------------------------------------------------------------------------
# Inline callbacks
# ---------------------------------------------------------------------------
def test_owner_callback_is_queued(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_callback("approve:17"))
    assert resp.get_json()["queued"] == "callback"
    assert _commands(tmp_path)[0]["text"] == "/approve 17"


def test_stranger_callback_is_denied(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_callback("approve:17", from_id=STRANGER))
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_callback_without_sender_is_denied(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_callback("approve:17", from_id=None))
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_callback_forged_from_field_is_denied(client, appmod, tmp_path, monkeypatch):
    # A crafted callback that names the owner in data still fails: the sender
    # id comes from callback.from, not from the payload.
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post(
        "/api/telegram/webhook",
        json=_callback(f"approve:17:{OWNER}", from_id=STRANGER),
    )
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


# ---------------------------------------------------------------------------
# Webhook shared secret (separate from owner identity)
# ---------------------------------------------------------------------------
def test_missing_webhook_secret_in_production_fails_closed(client, monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"))
    assert resp.status_code == 401


def test_invalid_webhook_secret_is_rejected(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"), headers={HEADER: "wrong"})
    assert resp.status_code == 401


def test_valid_secret_but_unauthorized_sender_is_denied(client, appmod, tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post(
        "/api/telegram/webhook",
        json=_msg("/approve 7", from_id=STRANGER),
        headers={HEADER: "s3cret"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["denied"] == "not-owner"
    assert _commands(tmp_path) == []


def test_secret_unset_outside_production_still_open(client, monkeypatch):
    monkeypatch.delenv("GENESIS_ENV", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/start"))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Harness side: a queued command without an owner sender never merges
# ---------------------------------------------------------------------------
def _load_self_improve():
    spec = importlib.util.spec_from_file_location("self_improve", ROOT / "scripts" / "self_improve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_harness_filters_non_owner_entries(monkeypatch):
    module = _load_self_improve()
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    payload = {
        "commands": [
            {"text": "/approve 7", "from_id": STRANGER},   # stranger
            {"text": "/approve 8", "from_id": OWNER},       # owner
            {"text": "/approve 9"},                          # no sender at all
            {"text": "/approve 10", "from_id": OWNER},      # owner
        ]
    }
    monkeypatch.setattr(module, "_space_get", lambda url: json.dumps(payload))
    assert module._incoming_commands() == ["/approve 8", "/approve 10"]


def test_harness_with_no_owner_configured_refuses_all(monkeypatch):
    module = _load_self_improve()
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    payload = {"commands": [{"text": "/approve 7", "from_id": OWNER}]}
    monkeypatch.setattr(module, "_space_get", lambda url: json.dumps(payload))
    assert module._incoming_commands() == []


def test_harness_never_merges_for_a_non_owner_entry(monkeypatch):
    module = _load_self_improve()
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    payload = {"commands": [{"text": "/approve 7", "from_id": STRANGER}]}
    monkeypatch.setattr(module, "_space_get", lambda url: json.dumps(payload))
    monkeypatch.setattr(module, "_ack_commands", lambda ids: None)
    monkeypatch.setattr(module, "_notify", lambda *a, **k: None)

    merged: list[str] = []

    class _FakeTransport:
        def approve(self, token, reason=""):
            merged.append(token)
            return f"Approved {token}"

        def reject(self, token, reason=""):
            merged.append(token)
            return f"Rejected {token}"

        def list_open(self):
            return []

        def status(self, token):
            return ""

    monkeypatch.setattr(module, "_transport", lambda: _FakeTransport())
    module.process_approvals()
    assert merged == []
