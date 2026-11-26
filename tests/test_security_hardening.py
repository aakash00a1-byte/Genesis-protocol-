"""Security hardening: gated diagnostics, safe error text, code execution consent.

Three contracts:

1. ``/api/diagnostics`` and ``/api/debug`` name which provider credentials exist
   and carry provider error text, so they are owner-only (or shared-secret) and
   fail closed. ``/api/health`` stays public.
2. A provider error body is reduced to its human message before it reaches a
   status field: account, plan and request-identifier detail never appears.
3. A fenced code block in a message is data. It is parked, never executed, and
   runs once only after an explicit ``/approve_code <id>`` for that exact block.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web.app as appmod
from genesis_protocol.agentic.code_consent import CodeConsentStore
from genesis_protocol.ai.providers.base_provider import sanitize_error

GATED_ENDPOINTS = ("/api/diagnostics", "/api/debug")


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture
def consent(tmp_path, monkeypatch):
    """A store with its own file, installed as the process-wide instance."""
    import genesis_protocol.agentic.code_consent as consent_module

    store = CodeConsentStore(path=str(tmp_path / "code_requests.json"))
    monkeypatch.setattr(consent_module, "_default", store)
    return store


# --- 1. owner-only diagnostics ---------------------------------------------
@pytest.mark.parametrize("endpoint", GATED_ENDPOINTS)
def test_gated_endpoints_refuse_anonymous_callers(client, monkeypatch, endpoint):
    monkeypatch.delenv("DIAGNOSTICS_SECRET", raising=False)
    response = client.get(endpoint)

    assert response.status_code == 403
    assert response.is_json
    assert "error" in response.get_json()


@pytest.mark.parametrize("endpoint", GATED_ENDPOINTS)
def test_gated_endpoints_accept_the_shared_secret(client, monkeypatch, endpoint):
    monkeypatch.setenv("DIAGNOSTICS_SECRET", "diagnostics-secret-value")

    ok = client.get(endpoint, headers={"X-Genesis-Secret": "diagnostics-secret-value"})
    wrong = client.get(endpoint, headers={"X-Genesis-Secret": "not-the-secret"})

    assert ok.status_code == 200
    assert wrong.status_code == 403


def test_diagnostics_accepts_an_owner_session(client, monkeypatch):
    monkeypatch.delenv("DIAGNOSTICS_SECRET", raising=False)
    monkeypatch.setattr(appmod, "_is_owner", lambda user_id: True)
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "owner"
        sess["role"] = "admin"

    assert client.get("/api/diagnostics").status_code == 200


def test_health_stays_public(client, monkeypatch):
    monkeypatch.delenv("DIAGNOSTICS_SECRET", raising=False)

    assert client.get("/api/health").status_code == 200


def test_debug_reports_the_running_commit_not_a_literal(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTICS_SECRET", "diagnostics-secret-value")
    monkeypatch.setenv("GENESIS_COMMIT_SHA", "deadbeefcafe1234")

    body = client.get("/api/debug",
                      headers={"X-Genesis-Secret": "diagnostics-secret-value"}).get_json()

    assert body["commit"] == "deadbeefcafe1234"
    assert body["commit"] != "417a557"


def test_running_commit_is_unknown_without_env_or_marker(monkeypatch):
    for var in ("GENESIS_COMMIT_SHA", "GIT_COMMIT_SHA", "SOURCE_COMMIT_SHA"):
        monkeypatch.delenv(var, raising=False)

    assert appmod._running_commit() in ("unknown",) or len(appmod._running_commit()) >= 7


# --- 2. provider error text --------------------------------------------------
def test_provider_error_body_is_reduced_to_its_message():
    raw = (
        'Mistral API error: 402 - {"object":"error","message":"You need a '
        'subscription to access this API.","type":"invalid_request_error",'
        '"param":null,"code":"2314","raw_status_code":402}'
    )

    summary = sanitize_error(raw)

    assert "You need a subscription to access this API." in summary
    assert "raw_status_code" not in summary
    assert "2314" not in summary
    assert "invalid_request_error" not in summary
    assert summary.startswith("Mistral API error: 402")


def test_unparseable_body_is_withheld_not_passed_through():
    summary = sanitize_error("openrouter API error: 400 - {not json at all}")

    assert "not json at all" not in summary
    assert "details withheld" in summary


def test_sanitize_error_still_redacts_credentials():
    summary = sanitize_error("Authorization: Bearer abc123def456ghi789")

    assert "abc123def456ghi789" not in summary


def test_sanitize_error_keeps_our_own_numbers():
    summary = sanitize_error("prompt too large (~198011 tokens, window 32768)")

    assert "198011" in summary and "32768" in summary


# --- 3. code execution consent ----------------------------------------------
def test_parked_code_cannot_run_until_it_is_claimed(consent):
    request = consent.request(7, "print(6 * 7)")

    assert consent.get(7, request.request_id) is not None
    assert consent.claim(8, request.request_id)[0] is None, "another user's approval"
    assert consent.claim(7, request.request_id, "print(1)")[0] is None, "different code"

    claimed, reason = consent.claim(7, request.request_id, "print(6 * 7)")
    assert claimed is not None and reason == "approved"


def test_an_approval_is_single_use(consent):
    request = consent.request(7, "print(6 * 7)")
    assert consent.claim(7, request.request_id)[0] is not None

    second, reason = consent.claim(7, request.request_id)

    assert second is None
    assert "already used" in reason


def test_an_approval_expires(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "expired.json"), ttl_seconds=-1)
    request = store.request(7, "print(6 * 7)")

    claimed, reason = store.claim(7, request.request_id)

    assert claimed is None
    assert reason == "approval expired"


def test_pending_lists_only_this_users_live_requests(consent):
    mine = consent.request(7, "print(1)")
    consent.request(8, "print(2)")

    pending = consent.pending(7)

    assert [r.request_id for r in pending] == [mine.request_id]


async def test_code_tool_refuses_without_an_approval(consent):
    from genesis_protocol.ai.tool_system import get_tool_system

    result = await get_tool_system().execute_tool(
        "code_execution", {"code": "print(6 * 7)"}
    )

    assert result.success is False
    assert "approval" in (result.error or "").lower()


async def test_code_tool_runs_once_with_a_valid_approval(consent):
    from genesis_protocol.ai.tool_system import get_tool_system

    request = consent.request(7, "print(6 * 7)")
    tool_system = get_tool_system()

    first = await tool_system.execute_tool("code_execution", {
        "code": "print(6 * 7)", "approval_id": request.request_id, "user_id": 7,
    })
    second = await tool_system.execute_tool("code_execution", {
        "code": "print(6 * 7)", "approval_id": request.request_id, "user_id": 7,
    })

    assert first.success is True
    assert "42" in (first.data or {}).get("output", "")
    assert second.success is False
    assert "already used" in (second.error or "")


async def test_chat_never_executes_a_pasted_block(consent, monkeypatch):
    """The chat tool path must park the block and call nothing."""
    from genesis_protocol.ai.agent import get_genesis_agent

    agent = get_genesis_agent()

    async def must_not_run(*args, **kwargs):
        raise AssertionError("code_execution must not run on selection")

    class Allowed:
        allowed = True
        reason = "test"

    monkeypatch.setattr(agent, "_authorize_chat_tool", lambda *a, **k: Allowed())
    monkeypatch.setattr(agent.tool_system, "execute_tool", must_not_run)

    message = "here is the report\n```python\nprint(6 * 7)\n```\n"
    _text, failures = await agent._execute_tools(["code_execution"], message, 7)

    assert any("NOT run" in failure for failure in failures)
    assert any("/approve_code " in failure for failure in failures)
    assert consent.pending(7), "the block should be parked for approval"


def test_approve_code_command_is_parsed_exactly():
    from genesis_protocol.ai.agent import get_genesis_agent

    agent = get_genesis_agent()

    assert agent._parse_approve_code("/approve_code abc123") == "abc123"
    assert agent._parse_approve_code("  /approve_code abc123  ") == "abc123"
    assert agent._parse_approve_code("please /approve_code abc123") is None
    assert agent._parse_approve_code("what is /approve_code") is None
