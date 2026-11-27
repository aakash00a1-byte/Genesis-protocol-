"""R8: session integrity and invalidation, without ever handling the secret.

The startup refusal for a missing/weak ``SECRET_KEY`` is covered by
``tests/test_web_secret_key_startup.py``. This file covers what a *running*
app must do: reject a cookie signed with any other key, reject a cookie minted
with the documented public default, invalidate the session on logout, and keep
a session that names a non-owner out of owner-only endpoints.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from flask import Flask
from flask.sessions import SecureCookieSessionInterface

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STRONG_KEY = "k" * 48
PUBLIC_DEFAULT = "genesis-secret-key-change-in-production"
OWNER = 1


@pytest.fixture()
def appmod(tmp_path, monkeypatch):
    import genesis_protocol.agentic.policy as policy_module

    monkeypatch.setenv("SECRET_KEY", STRONG_KEY)
    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(OWNER))
    monkeypatch.setenv("GLUTEN_MEMORY_DB", str(tmp_path / "mem.db"))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(policy_module, "_default", None)
    module = importlib.import_module("web.app")
    module = importlib.reload(module)
    module.app.config["TESTING"] = True
    return module


@pytest.fixture()
def client(appmod):
    return appmod.app.test_client()


def _cookie_signed_with(key: str, data: dict, cookie_name: str = "session") -> str:
    """Mint a session cookie with an arbitrary key, as an attacker would."""
    scratch = Flask("scratch")
    scratch.secret_key = key
    serializer = SecureCookieSessionInterface().get_signing_serializer(scratch)
    return serializer.dumps(data)


def _login(client) -> str:
    response = client.post("/api/auth/login", json={
        "username": "admin", "password": "genesis-admin-2024"})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["token"]


def test_the_app_uses_the_configured_key_and_not_the_public_default(appmod):
    assert appmod.app.secret_key == STRONG_KEY
    assert appmod.app.secret_key != PUBLIC_DEFAULT


def test_a_cookie_signed_with_the_public_default_is_rejected(appmod, client):
    cookie = _cookie_signed_with(PUBLIC_DEFAULT, {"user_id": OWNER})

    client.set_cookie("session", cookie)
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_a_cookie_signed_with_another_key_is_rejected(appmod, client):
    cookie = _cookie_signed_with("attacker-chosen-key-0123456789", {"user_id": OWNER})

    client.set_cookie("session", cookie)
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_a_garbage_cookie_is_rejected(appmod, client):
    client.set_cookie("session", "not-a-signed-cookie")

    assert client.get("/api/auth/me").status_code == 401


def test_logout_invalidates_the_session(appmod, client):
    _login(client)
    assert client.get("/api/auth/me").status_code == 200

    client.post("/api/auth/logout")

    assert client.get("/api/auth/me").status_code == 401


def test_a_validly_signed_non_owner_session_cannot_reach_owner_endpoints(appmod, client):
    with client.session_transaction() as session:
        session["user_id"] = 999

    # A session naming a user that does not exist is rejected outright.
    assert client.get("/api/auth/me").status_code == 404
    assert client.get("/api/diagnostics").status_code == 403
    assert client.get("/api/agents").status_code == 403
    assert client.get("/api/guardian/status").status_code == 403


def test_a_validly_signed_owner_session_is_accepted(appmod, client):
    with client.session_transaction() as session:
        session["user_id"] = OWNER

    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/diagnostics").status_code == 200


def test_a_bearer_token_never_falls_back_to_the_session(appmod, client):
    """A bad Bearer token must not be rescued by a valid cookie."""
    with client.session_transaction() as session:
        session["user_id"] = OWNER

    response = client.get("/api/memory", headers={"Authorization": "Bearer genesis_mobile_1_0"})

    assert response.status_code == 401
