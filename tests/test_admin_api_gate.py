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


class TestAdminPasswordProvisioning:
    """ADMIN_PASSWORD is the source of truth for the admin account.

    The Space sets ADMIN_PASSWORD, so the documented default
    ('genesis-admin-2024') never matched the seeded hash, and rotating the
    secret never took effect because seeding only ran when no admin existed.
    """

    def _hash(self, db, username="admin"):
        import sqlite3
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        conn.close()
        return row["password_hash"]

    def test_fresh_db_uses_admin_password(self, tmp_path, monkeypatch):
        from werkzeug.security import check_password_hash

        monkeypatch.setenv("ADMIN_PASSWORD", "SecretOne123")
        import web.app as appmod

        appmod.DATABASE = str(tmp_path / "a.db")
        appmod.init_db()
        assert check_password_hash(self._hash(appmod.DATABASE), "SecretOne123")

    def test_rotated_admin_password_takes_effect(self, tmp_path, monkeypatch):
        from werkzeug.security import check_password_hash

        import web.app as appmod

        appmod.DATABASE = str(tmp_path / "b.db")
        monkeypatch.setenv("ADMIN_PASSWORD", "SecretOne123")
        appmod.init_db()
        monkeypatch.setenv("ADMIN_PASSWORD", "SecretTwo456")
        appmod.init_db()
        digest = self._hash(appmod.DATABASE)
        assert check_password_hash(digest, "SecretTwo456")
        assert not check_password_hash(digest, "SecretOne123")

    def test_default_used_only_without_admin_password(self, tmp_path, monkeypatch):
        from werkzeug.security import check_password_hash

        import web.app as appmod

        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
        appmod.DATABASE = str(tmp_path / "c.db")
        appmod.init_db()
        assert check_password_hash(self._hash(appmod.DATABASE), "genesis-admin-2024")
