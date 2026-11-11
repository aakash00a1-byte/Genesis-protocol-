"""Mobile bearer-token authentication must be unforgeable and fail closed.

`login_required` accepts a `Bearer genesis_mobile_<id>_<issued_at>_<sig>` token.
The signature is the only thing that proves the token was issued by this
server, so these tests pin the two halves of the contract:

* a forged, tampered, malformed or expired token is rejected with 401, and
* a token this server issued is accepted.

A regression here is an account-takeover: any caller could name any user id.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def appmod(monkeypatch, tmp_path):
    import web.app as module

    monkeypatch.setattr(module, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(module, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(module, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    module.app.config["TESTING"] = True
    return module


@pytest.fixture
def client(appmod):
    return appmod.app.test_client()


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_no_credentials_is_rejected(client):
    assert client.get("/api/chat/conversations").status_code == 401


def test_forged_legacy_token_is_rejected(client):
    # The exact shape the old code accepted: no signature at all.
    resp = client.get("/api/chat/conversations", headers=_bearer("genesis_mobile_1_0"))
    assert resp.status_code == 401


def test_forged_token_for_any_user_is_rejected(client):
    resp = client.get(
        "/api/chat/conversations", headers=_bearer("genesis_mobile_999_anything")
    )
    assert resp.status_code == 401


def test_malformed_bearer_is_rejected(client):
    assert client.get("/api/chat/conversations", headers=_bearer("garbage")).status_code == 401


def test_server_issued_token_is_accepted(client, appmod):
    token = appmod._issue_mobile_token(1)
    resp = client.get("/api/chat/conversations", headers=_bearer(token))
    assert resp.status_code == 200


def test_tampered_signature_is_rejected(client, appmod):
    token = appmod._issue_mobile_token(1)
    resp = client.get("/api/chat/conversations", headers=_bearer(token[:-4] + "dead"))
    assert resp.status_code == 401


def test_tampered_user_id_is_rejected(client, appmod):
    token = appmod._issue_mobile_token(1)
    forged = token.replace("_1_", "_2_", 1)
    resp = client.get("/api/chat/conversations", headers=_bearer(forged))
    assert resp.status_code == 401


def test_expired_token_is_rejected(client, appmod):
    stale = appmod._issue_mobile_token(1, issued_at=int(time.time()) - 40 * 24 * 3600)
    resp = client.get("/api/chat/conversations", headers=_bearer(stale))
    assert resp.status_code == 401


def test_verify_helper_roundtrip(appmod):
    assert appmod._verify_mobile_token(appmod._issue_mobile_token(7)) == 7
    assert appmod._verify_mobile_token("genesis_mobile_7_0") is None
    assert appmod._verify_mobile_token("nonsense") is None


def test_debug_telegram_requires_secret(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert client.get("/api/debug/telegram").status_code == 401
    ok = client.get(
        "/api/debug/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret"},
    )
    assert ok.status_code == 200
