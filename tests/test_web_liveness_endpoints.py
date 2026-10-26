"""Liveness endpoints on the Space: /api/health, /api/version, /api/status.

These three routes have no side effects and are the contract every monitor
depends on:

  * ``scripts/health_check.py`` treats ``status == "healthy"`` as the Space
    being up, and pages the owner when it is not.
  * ``web/render.yaml`` points ``healthCheckPath`` at ``/api/health``.
  * ``scripts/release_test.py`` asserts the keys each response must carry.
  * ``scripts/relay_loop.py`` reads ``/api/status``.

Renaming a field here does not break an import, so nothing catches it until
the owner receives a false "Space unreachable" alert. These tests pin the
exact keys those callers read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_health_reports_healthy(client):
    """health_check.py pages the owner unless this says exactly 'healthy'."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "healthy"


def test_health_needs_no_auth(client):
    """render.yaml probes this path unauthenticated; it must stay open."""
    assert client.get("/api/health").status_code == 200


def test_version_carries_release_identity(client):
    """release_test.py asserts version and build_date are present."""
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "version" in body
    assert "build_date" in body
    assert body["version"]


def test_status_carries_metrics(client):
    """release_test.py asserts metrics and status; relay_loop reads this."""
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert "metrics" in body
    assert "uptime_seconds" in body["metrics"]
