"""Real tests for the Telegram runtime/GitHub commands and read-only GitHub view.

These drive the actual Flask webhook route and the real command module. The
GitHub calls are injected through the module's ``http`` seam so no network is
needed; the parsing/formatting and gating logic under test is real code, not a
mock of it.

What is pinned:
* ``/capabilities`` and ``/status`` report runtime facts from the same source as
  ``/api/identity`` (no stale "Groq-powered" blurb), and never leak a token.
* ``/github`` and ``/prs`` reflect the GitHub read result, including a stated
  reason when the connection is unknown.
* ``/task`` and ``/task_status`` are owner-gated and write durable state.
* A bare ``/status`` is GLUTEN status; ``/status <id>`` still falls through to
  the update transport.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OWNER = 1863492058
STRANGER = 999999999


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", str(OWNER))
    # Keep the durable task store inside the test's temp dir.
    monkeypatch.setenv("GLUTEN_TASK_DB", str(tmp_path / "agent_tasks.json"))
    import genesis_protocol.agentic.tasks as tasks

    monkeypatch.setattr(tasks, "_default", None)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _msg(text, uid=OWNER):
    return {"message": {"text": text, "from": {"id": uid}, "chat": {"id": uid}}}


def _last_reply(path):
    if not Path(path).exists():
        return ""
    data = json.loads(Path(path).read_text())
    return data[-1]["text"] if data else ""


def _send(client, text, uid=OWNER):
    resp = client.post("/api/telegram/webhook", json=_msg(text, uid))
    assert resp.status_code == 200
    return resp.get_json()


def _reply_text(client, text, uid=OWNER):
    resp = client.post("/api/telegram/webhook", json=_msg(text, uid))
    assert resp.status_code == 200
    import web.app as appmod

    return _last_reply(appmod.TELEGRAM_REPLY_QUEUE)


class TestCapabilitiesCommand:
    def test_reports_real_tool_count(self, client):
        from genesis_protocol.agentic.identity import describe_runtime

        text = _reply_text(client, "/capabilities")
        assert f"tools: {len(describe_runtime()['tools'])} registered" in text

    def test_never_leaks_a_token(self, client, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_SUPERSECRETVALUE")
        text = _reply_text(client, "/capabilities")
        assert "SUPERSECRET" not in text
        assert "ghp_" not in text


class TestStatusCommand:
    def test_bare_status_reports_runtime_provider(self, client):
        from genesis_protocol.agentic.identity import describe_runtime

        runtime = describe_runtime()
        text = _reply_text(client, "/status")
        assert "GLUTEN status" in text
        if runtime.get("default_provider"):
            assert runtime["default_provider"] in text

    def test_status_does_not_claim_a_hardcoded_provider(self, client):
        # The old blurb hardcoded "Groq-powered" regardless of the real model.
        text = _reply_text(client, "/status")
        assert "Groq-powered" not in text

    def test_status_with_id_falls_through_to_updates(self, client):
        # "/status <id>" is the update lookup, not GLUTEN status: it must be
        # parked for the harness, not answered here.
        body = _send(client, "/status 3")
        assert body.get("queued") == "command"


class TestTaskCommandsOwnerGated:
    def test_owner_can_create_and_read_a_task(self, client):
        import web.app as appmod

        created = _reply_text(client, "/task check the deploy logs")
        assert "record ho gaya" in created
        task_id = created.split("Task ", 1)[1].split()[0]

        status = _last_reply_after(client, f"/task_status {task_id}")
        assert task_id in status
        assert "check the deploy logs" in status
        # Durable store actually holds it.
        from genesis_protocol.agentic.tasks import get_task_store

        assert get_task_store().get(OWNER, task_id) is not None

    def test_stranger_is_denied(self, client):
        assert "sirf owner" in _reply_text(client, "/task do something", uid=STRANGER)
        assert "sirf owner" in _reply_text(client, "/task_status", uid=STRANGER)

    def test_stranger_cannot_create_a_durable_task(self, client):
        from genesis_protocol.agentic.tasks import get_task_store

        _reply_text(client, "/task stranger task", uid=STRANGER)
        assert get_task_store().list_tasks(STRANGER) == []


def _last_reply_after(client, text):
    return _reply_text(client, text)


class TestGitHubStatusModule:
    def test_missing_token_is_reported_not_guessed(self, monkeypatch):
        from genesis_protocol.integrations import github_status

        for name in github_status._TOKEN_ENV_ORDER:
            monkeypatch.delenv(name, raising=False)
        data = github_status.status()
        assert data["connected"] is False
        assert data["token_present"] is False
        assert "token" in data["reason"]

    def test_connected_read_parses_open_prs(self, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "x")

        def fake_http(url):
            if url.endswith("/pulls?state=open&per_page=50"):
                return [
                    {"number": 5, "title": "fix thing", "head": {"ref": "agent/x"},
                     "html_url": "u", "draft": False}
                ]
            return {"full_name": github_status.REPO, "default_branch": "main",
                    "private": False, "permissions": {"push": True, "admin": False}}

        data = github_status.status(http=fake_http)
        assert data["connected"] is True
        assert data["default_branch"] == "main"
        assert data["permissions"] == {"push": True, "admin": False}
        assert [p["number"] for p in data["pulls"]] == [5]

    def test_api_error_is_reported_as_a_reason(self, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "x")

        def boom(url):
            raise RuntimeError("HTTP 403")

        data = github_status.status(http=boom)
        assert data["connected"] is False
        assert "HTTP 403" in data["reason"]

    def test_format_never_includes_the_token(self, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "ghp_TOPSECRET")

        def fake_http(url):
            if "pulls" in url:
                return []
            return {"full_name": github_status.REPO, "default_branch": "main",
                    "permissions": {}}

        text = github_status.format_status(github_status.status(http=fake_http))
        assert "TOPSECRET" not in text
        assert "ghp_" not in text


class TestGitHubCommands:
    def test_github_command_reports_connection(self, client, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "x")

        def fake_http(url):
            if "pulls" in url:
                return [{"number": 9, "title": "agent pr", "head": {"ref": "agent/y"},
                         "html_url": "u", "draft": False}]
            return {"full_name": github_status.REPO, "default_branch": "main",
                    "permissions": {}}

        monkeypatch.setattr(github_status, "_default_http", fake_http)
        text = _reply_text(client, "/github")
        assert "CONNECTED" in text
        assert "#9 agent pr" in text

    def test_prs_command_lists_open_prs(self, client, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "x")
        monkeypatch.setattr(
            github_status, "_default_http",
            lambda url: [{"number": 2, "title": "two", "head": {"ref": "agent/z"},
                          "html_url": "u", "draft": True}]
            if "pulls" in url else
            {"full_name": github_status.REPO, "default_branch": "main", "permissions": {}},
        )
        text = _reply_text(client, "/prs")
        assert "Open PRs: 1" in text
        assert "#2 two (draft)" in text

    def test_prs_when_not_connected_states_reason(self, client, monkeypatch):
        from genesis_protocol.integrations import github_status

        for name in github_status._TOKEN_ENV_ORDER:
            monkeypatch.delenv(name, raising=False)
        text = _reply_text(client, "/prs")
        assert "NOT CONNECTED" in text


class TestGitHubWebEndpoint:
    def test_api_github_is_read_only_and_secret_free(self, client, monkeypatch):
        from genesis_protocol.integrations import github_status

        monkeypatch.setenv("GITHUB_TOKEN", "ghp_WEBTEST")
        monkeypatch.setattr(
            github_status, "_default_http",
            lambda url: [{"number": 1, "title": "t", "head": {"ref": "agent/a"},
                          "html_url": "u", "draft": False}]
            if "pulls" in url else
            {"full_name": github_status.REPO, "default_branch": "main", "permissions": {}},
        )
        resp = client.get("/api/github")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["connected"] is True
        assert body["default_branch"] == "main"
        assert [p["number"] for p in body["pulls"]] == [1]
        assert "ghp_" not in json.dumps(body)
        assert "WEBTEST" not in json.dumps(body)
