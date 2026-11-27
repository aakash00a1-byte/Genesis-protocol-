"""Adversarial tests for the PR #90 remediation (F1-F7).

Every test attacks the gate rather than describing it:

* a non-owner driving ``AgentLoop`` directly (no web route in the path);
* an owner with no consent record;
* a forged ``owner_approved`` flag, at the loop and at the HTTP route;
* replayed, expired, cross-user and code-mismatched consent;
* shell metacharacters, ``bash -c``, command substitution and base64;
* credential-shaped code, and plaintext left behind after a claim;
* anonymous access to every diagnostic/test endpoint.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import genesis_protocol.agentic.code_consent as consent_module
from genesis_protocol.agentic.agent_loop import AgentLoop
from genesis_protocol.agentic.code_consent import CodeConsentError, CodeConsentStore
from genesis_protocol.agentic.policy import AgentPolicy

OWNER = 1
NON_OWNER = 2


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("GLUTEN_CODE_REQUESTS", str(tmp_path / "consent.json"))
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    monkeypatch.setattr(consent_module, "_default", store)
    monkeypatch.delenv("GLUTEN_ALLOW_SHELL_COMMANDS", raising=False)
    return store


def _loop(owner_ids=(OWNER,)):
    return AgentLoop(policy=AgentPolicy(owner_ids=set(owner_ids)))


# --- F1: the loop itself must refuse, not just the web route ----------------
def test_non_owner_direct_agent_loop_execution_is_refused(isolated):
    code = "print(41 + 1)"
    approval = isolated.request(NON_OWNER, code)  # even a valid record is not enough

    result = _loop().run(
        user_id=NON_OWNER,
        goal="print 42",
        steps=[{"type": "execute_code", "code": code, "approval_id": approval.request_id}],
    )
    step = result["steps"][0]

    assert step["executed"] is False
    assert step["denied"] is True
    assert "is not the owner" in step["error"]
    assert "stdout" not in step


def test_no_owner_configured_refuses_code_for_everyone(isolated):
    code = "print(1)"
    approval = isolated.request(OWNER, code)

    result = _loop(owner_ids=()).run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": code, "approval_id": approval.request_id}],
    )

    assert result["steps"][0]["executed"] is False
    assert "no owner is configured" in result["steps"][0]["error"]


def test_owner_without_consent_is_refused(isolated):
    result = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": "print(41 + 1)"}],
    )
    step = result["steps"][0]

    assert step["executed"] is False
    assert "approval record is required" in step["error"]


def test_owner_with_consent_runs_once(isolated):
    code = "print(41 + 1)"
    approval = isolated.request(OWNER, code)

    first = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": code, "approval_id": approval.request_id}],
    )
    replay = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": code, "approval_id": approval.request_id}],
    )

    assert first["steps"][0]["stdout"].strip() == "42"
    assert replay["steps"][0]["executed"] is False
    assert "already used" in replay["steps"][0]["error"]


# --- F2: a client flag is never authority ----------------------------------
def test_forged_owner_approved_flag_does_not_authorise_a_non_owner(isolated):
    code = "print(41 + 1)"
    approval = isolated.request(NON_OWNER, code)

    result = _loop().run(
        user_id=NON_OWNER, goal="x", owner_approved=True,
        steps=[{"type": "execute_code", "code": code, "approval_id": approval.request_id}],
    )
    assert result["steps"][0]["executed"] is False

    # The same forged flag on a consent-requiring tool is refused too.
    tool_result = _loop().run(
        user_id=NON_OWNER, goal="x", owner_approved=True,
        steps=[{"type": "tool", "tool": "python", "params": {"code": code}}],
    )
    assert tool_result["steps"][0]["success"] is False
    assert "not the owner" in tool_result["steps"][0]["error"]


def test_consent_requiring_tool_needs_its_own_record(isolated):
    code = "print(41 + 1)"
    no_record = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "tool", "tool": "python", "params": {"code": code}}],
    )
    assert no_record["steps"][0]["success"] is False
    assert "approval record is required" in no_record["steps"][0]["error"]

    approval = isolated.request(OWNER, code)
    with_record = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "tool", "tool": "python",
                "params": {"code": code, "approval_id": approval.request_id}}],
    )
    assert with_record["steps"][0]["result"]["stdout"].strip() == "42"


def test_http_route_ignores_the_owner_approved_body_field(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_MEMORY_DB", str(tmp_path / "mem.db"))
    monkeypatch.setenv("GLUTEN_TASK_DB", str(tmp_path / "tasks.json"))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    import genesis_protocol.agentic.policy as policy_module

    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(OWNER))
    monkeypatch.setattr(policy_module, "_default", None)
    appmod = importlib.import_module("web.app")
    importlib.reload(appmod)
    appmod.app.config["TESTING"] = True
    client = appmod.app.test_client()

    token = client.post("/api/auth/login", json={
        "username": "admin", "password": "genesis-admin-2024"}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    # The admin row's id depends on the database this run uses; make that id
    # the owner instead of assuming 1.
    admin_id = client.get("/api/auth/me", headers=headers).get_json()["user"]["id"]
    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(admin_id))
    monkeypatch.setattr(policy_module, "_default", None)
    code = "print(41 + 1)"

    # The owner's forged flag does not replace the consent record...
    resp = client.post("/api/agent/run", headers=headers, json={
        "goal": "x", "owner_approved": True,
        "steps": [{"type": "execute_code", "code": code}],
    })
    assert resp.get_json()["steps"][0]["executed"] is False

    # ...and the same flag on a consent-requiring tool does not either.
    resp = client.post("/api/agent/run", headers=headers, json={
        "goal": "x", "owner_approved": True,
        "steps": [{"type": "tool", "tool": "python", "params": {"code": code}}],
    })
    step = resp.get_json()["steps"][0]
    assert step["success"] is False
    assert "approval record is required" in step["error"]


# --- F4: consent record integrity ------------------------------------------
def test_expired_consent_is_refused(isolated, tmp_path, monkeypatch):
    store = CodeConsentStore(path=str(tmp_path / "expired.json"), ttl_seconds=-1)
    monkeypatch.setattr(consent_module, "_default", store)
    approval = store.request(OWNER, "print(1)")

    result = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": "print(1)",
                "approval_id": approval.request_id}],
    )
    assert result["steps"][0]["executed"] is False
    assert "expired" in result["steps"][0]["error"]


def test_modified_code_after_approval_is_refused(isolated):
    approval = isolated.request(OWNER, "print('safe')")

    result = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": "print('evil')",
                "approval_id": approval.request_id}],
    )
    assert result["steps"][0]["executed"] is False
    assert "does not match" in result["steps"][0]["error"]


def test_another_users_consent_is_refused(isolated):
    approval = isolated.request(NON_OWNER, "print(1)")

    result = _loop().run(
        user_id=OWNER, goal="x",
        steps=[{"type": "execute_code", "code": "print(1)",
                "approval_id": approval.request_id}],
    )
    assert result["steps"][0]["executed"] is False
    assert "another user" in result["steps"][0]["error"]


def test_credential_shaped_code_is_not_parked(isolated):
    for code in (
        'API_KEY = "sk-proj-abcdef0123456789abcdef"',
        'token = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"',
        'url = "https://x.test/?key=AIzaSyD-abcdefghijklmnopqrstuv"',
    ):
        with pytest.raises(CodeConsentError):
            isolated.request(OWNER, code)
    assert not isolated.pending(OWNER)
    assert not Path(isolated.path).exists() or "sk-proj" not in Path(isolated.path).read_text()


def test_ordinary_code_with_a_token_variable_still_parks(isolated):
    """The scanner must not refuse every block that mentions a token."""
    code = 'token = get_token()\nsecret = load_secret()\nprint(token)'

    approval = isolated.request(OWNER, code)

    assert approval.request_id
    assert approval.code == code


def test_claim_removes_the_plaintext_and_cleanup_prunes(isolated):
    code = "print('hello')"
    approval = isolated.request(OWNER, code)
    assert code in Path(isolated.path).read_text()

    claimed, reason = isolated.claim(OWNER, approval.request_id, code)
    assert claimed is not None and reason == "approved"
    stored = json.loads(Path(isolated.path).read_text())["requests"][approval.request_id]
    assert stored["code"] == ""
    assert code not in Path(isolated.path).read_text()

    assert isolated.cleanup() >= 1
    assert json.loads(Path(isolated.path).read_text())["requests"] == {}


def test_cleanup_drops_expired_requests(tmp_path):
    store = CodeConsentStore(path=str(tmp_path / "old.json"), ttl_seconds=-1)
    store.request(OWNER, "print(1)")

    assert store.cleanup() == 1
    assert store.pending(OWNER) == []


# --- F3: shell execution ----------------------------------------------------
def _subprocess_tool():
    from genesis_protocol.tools.skill_tools import SubprocessTool

    return SubprocessTool()


def test_command_execution_is_disabled_by_default():
    result = _subprocess_tool().execute("echo hello")

    assert result["success"] is False
    assert "disabled by default" in result["error"]


def test_shell_metacharacters_are_inert_when_enabled(monkeypatch):
    monkeypatch.setenv("GLUTEN_ALLOW_SHELL_COMMANDS", "1")
    tool = _subprocess_tool()

    semicolon = tool.execute("echo SAFE; id")
    substitution = tool.execute("echo $(id)")
    backticks = tool.execute("echo `id`")
    pipe = tool.execute("echo aWQ= | base64 -d | sh")

    assert semicolon["stdout"].strip() == "SAFE; id"
    assert substitution["stdout"].strip() == "$(id)"
    assert backticks["stdout"].strip() == "`id`"
    assert pipe["stdout"].strip() == "aWQ= | base64 -d | sh"
    for result in (semicolon, substitution, backticks, pipe):
        assert "uid=" not in (result.get("stdout") or "")


@pytest.mark.parametrize("command", [
    'bash -c "id"',
    'sh -c "id"',
    'env bash -c "id"',
    'xargs -I{} sh -c "id"',
    'timeout 5 bash -c "id"',
    'python3 -c "import os; os.system(\'id\')"',
    'perl -e "system(\'id\')"',
    'node -e "require(\'child_process\').execSync(\'id\')"',
])
def test_shell_binaries_and_wrappers_are_refused(monkeypatch, command):
    monkeypatch.setenv("GLUTEN_ALLOW_SHELL_COMMANDS", "1")

    result = _subprocess_tool().execute(command)

    assert result["success"] is False
    assert "shell" in result["error"]
    assert "uid=" not in (result.get("stdout") or "")


def test_the_child_process_gets_no_inherited_credentials(monkeypatch):
    """An unsandboxed command must not see the process environment."""
    monkeypatch.setenv("GLUTEN_ALLOW_SHELL_COMMANDS", "1")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "a" * 30)

    result = _subprocess_tool().execute("printenv")

    assert result["success"] is True
    assert "GROQ_API_KEY" not in result["stdout"]


def test_privileged_commands_are_still_refused_with_the_flag_on(monkeypatch):
    monkeypatch.setenv("GLUTEN_ALLOW_SHELL_COMMANDS", "1")

    result = _subprocess_tool().execute("git push origin main")

    assert result["success"] is False
    assert "refused" in result["error"]


def test_cli_tools_no_longer_use_a_shell(monkeypatch):
    from genesis_protocol.tools.skill_tools import _cli

    tool = _cli("echo_cli", "echo")()
    injected = tool.execute(args='SAFE; id')

    assert injected["stdout"].strip() == "SAFE; id"
    assert "uid=" not in injected["stdout"]


# --- F5/F6: endpoints and error text ---------------------------------------
GATED_ENDPOINTS = ("/api/diagnostics", "/api/debug", "/api/test-417a557")


@pytest.fixture
def web_client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_MEMORY_DB", str(tmp_path / "mem.db"))
    monkeypatch.setenv("GLUTEN_TASK_DB", str(tmp_path / "tasks.json"))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("DIAGNOSTICS_SECRET", raising=False)
    appmod = importlib.import_module("web.app")
    importlib.reload(appmod)
    appmod.app.config["TESTING"] = True
    return appmod, appmod.app.test_client()


@pytest.mark.parametrize("endpoint", GATED_ENDPOINTS)
def test_every_diagnostic_endpoint_refuses_anonymous_callers(web_client, endpoint):
    _app, client = web_client

    response = client.get(endpoint)

    assert response.status_code == 403
    body = response.get_data(as_text=True)
    for needle in ("last_error", "provider", "API_KEY", "commit"):
        assert needle not in body


def test_test_endpoint_reports_no_commit_even_when_authorised(web_client, monkeypatch):
    appmod, client = web_client
    monkeypatch.setenv("DIAGNOSTICS_SECRET", "review-secret")

    body = client.get("/api/test-417a557",
                      headers={"X-Genesis-Secret": "review-secret"}).get_json()

    assert body["status"] == "ok"
    assert "commit" not in body


def test_billing_detail_is_not_echoed_in_last_error():
    from genesis_protocol.ai.providers.base_provider import sanitize_error

    mistral = sanitize_error(
        'Mistral API error: 402 - {"object":"error","message":"You need a '
        'subscription to access this API.","code":"2314","raw_status_code":402}'
    )
    credits = sanitize_error(
        'openrouter API error: 402 - {"error":{"message":"This request would '
        'exceed your remaining credits"}}'
    )

    for summary in (mistral, credits):
        assert "subscription" not in summary.lower()
        assert "credit" not in summary.lower()
        assert "plan or billing restriction" in summary
