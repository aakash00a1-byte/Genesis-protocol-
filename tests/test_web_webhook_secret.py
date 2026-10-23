"""Shared-secret enforcement on the Telegram webhook and reply queue.

`web/app.py` accepts an optional shared secret (TELEGRAM_WEBHOOK_SECRET,
header X-Telegram-Bot-Api-Secret-Token). These tests drive the real Flask
routes to hold both halves of the contract: with the secret configured a
missing or wrong header is rejected (401), the right header is accepted, and
with no secret configured the endpoint stays open so an existing deployment
does not break.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HEADER = "X-Telegram-Bot-Api-Secret-Token"


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _update(text="/start", chat_id=1863492058):
    return {"message": {"text": text, "from": {"id": chat_id}, "chat": {"id": chat_id}}}


def test_webhook_rejects_missing_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    resp = client.post("/api/telegram/webhook", json=_update())
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_webhook_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    resp = client.post("/api/telegram/webhook", json=_update(), headers={HEADER: "nope"})
    assert resp.status_code == 401


def test_webhook_accepts_matching_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    resp = client.post("/api/telegram/webhook", json=_update(), headers={HEADER: "s3cret"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_webhook_open_when_secret_unset(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    resp = client.post("/api/telegram/webhook", json=_update())
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_queue_enforces_same_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert client.get("/api/telegram/queue").status_code == 401
    ok = client.get("/api/telegram/queue", headers={HEADER: "s3cret"})
    assert ok.status_code == 200
    assert ok.get_json() == {"replies": [], "count": 0}
