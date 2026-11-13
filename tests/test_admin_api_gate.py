"""Admin-only API endpoints must answer JSON, never an HTML redirect.

Observed live: a logged-in non-admin calling GET /api/admin/stats got a 302 to
/chat (the HTML page) instead of a JSON 403, because ``admin_required`` only
checked ``request.is_json`` while ``login_required`` also treats any ``/api/``
path as a JSON caller. An API client (or a redirect-following one) reads that
302 as success, which hides the refusal.

These tests drive the real Flask routes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ADMIN_ENDPOINTS = (
    "/api/admin/stats",
    "/api/admin/users",
    "/api/admin/logs",
)


@pytest.fixture
def client():
    import web.app as appmod

    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _as_role(client, role):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "someone"
        sess["role"] = role


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_non_admin_gets_json_403_not_a_redirect(client, endpoint):
    _as_role(client, "user")
    r = client.get(endpoint)
    assert r.status_code == 403, f"{endpoint} returned {r.status_code}"
    assert r.is_json, f"{endpoint} answered HTML, not JSON"
    assert r.get_json().get("error") == "Admin access required"


@pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
def test_anonymous_api_caller_gets_json_401_not_a_redirect(client, endpoint):
    r = client.get(endpoint)
    assert r.status_code == 401, f"{endpoint} returned {r.status_code}"
    assert r.is_json, f"{endpoint} answered HTML, not JSON"


def test_admin_page_still_redirects_a_browser(client):
    """A non-API path keeps the HTML redirect for a human browser."""
    _as_role(client, "user")
    r = client.get("/admin")
    assert r.status_code in (301, 302), f"/admin returned {r.status_code}"
