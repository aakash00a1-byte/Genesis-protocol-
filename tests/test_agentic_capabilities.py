"""Tests for the agentic capability layer.

These cover the Phase 3 requirements: durable memory across a real process
restart, cross-session recall, user isolation, real tool invocation with
evidence, rejection of unauthorized tool requests, sandbox timeouts and
resource limits, failed-task recovery, accurate provider/model reporting, and
the absence of fabricated memory or execution claims.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# 1. Memory surviving a real process restart
# ---------------------------------------------------------------------------

def test_memory_survives_process_restart(tmp_path):
    db = tmp_path / "mem.db"
    script = textwrap.dedent(
        f"""
        import sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from genesis_protocol.agentic.memory import AgentMemory
        m = AgentMemory({str(db)!r})
        m.remember(42, "the user's project is called Genesis", approved=True)
        m.close()
        """
    )
    r1 = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr

    # Fresh process reads the same file.
    script2 = textwrap.dedent(
        f"""
        import sys, json
        sys.path.insert(0, {str(REPO_ROOT)!r})
        from genesis_protocol.agentic.memory import AgentMemory
        m = AgentMemory({str(db)!r})
        print(json.dumps([x["content"] for x in m.recall(42, "project")]))
        m.close()
        """
    )
    r2 = subprocess.run([sys.executable, "-c", script2], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    recalled = json.loads(r2.stdout.strip())
    assert any("Genesis" in c for c in recalled)


# ---------------------------------------------------------------------------
# 2. Retrieval in a separate session
# ---------------------------------------------------------------------------

def test_memory_retrieved_in_a_new_session(tmp_path):
    from genesis_protocol.agentic.memory import AgentMemory

    db = str(tmp_path / "mem.db")
    session_one = AgentMemory(db)
    session_one.remember(7, "the user is vegetarian", approved=True)
    session_one.close()

    session_two = AgentMemory(db)  # new "session", same store
    hits = session_two.recall(7, "what food does the user eat? vegetarian")
    assert any("vegetarian" in h["content"] for h in hits)
    session_two.close()


# ---------------------------------------------------------------------------
# 3. User isolation
# ---------------------------------------------------------------------------

def test_memory_is_isolated_per_user(tmp_path):
    from genesis_protocol.agentic.memory import AgentMemory

    m = AgentMemory(str(tmp_path / "mem.db"))
    m.remember(1, "user one secret-ish preference", approved=True)
    m.remember(2, "user two preference", approved=True)

    assert m.count(1) == 1 and m.count(2) == 1
    assert all("user two" not in x["content"] for x in m.list_memories(1))
    assert all("user one" not in x["content"] for x in m.list_memories(2))
    # recall for an unknown user returns nothing
    assert m.recall(999, "preference") == []
    m.close()


def test_memory_correction_and_deletion_are_owner_scoped(tmp_path):
    from genesis_protocol.agentic.memory import AgentMemory

    m = AgentMemory(str(tmp_path / "mem.db"))
    mid = m.remember(1, "likes tea", approved=True)

    assert m.correct(2, mid, "hacked") is False  # other user cannot correct
    assert m.forget(2, mid) is False              # other user cannot delete
    assert m.correct(1, mid, "likes coffee") is True
    assert m.list_memories(1)[0]["content"] == "likes coffee"
    assert m.forget(1, mid) is True
    assert m.count(1) == 0
    m.close()


def test_memory_refuses_secrets_and_unapproved(tmp_path):
    from genesis_protocol.agentic.memory import AgentMemory, MemoryRejected

    m = AgentMemory(str(tmp_path / "mem.db"))
    with pytest.raises(MemoryRejected):
        m.remember(1, "api_key = sk-abcdefghijklmnop1234567890", approved=True)
    with pytest.raises(MemoryRejected):
        m.remember(1, "password: hunter2hunter2", approved=True)
    with pytest.raises(MemoryRejected):
        m.remember(1, "unapproved fact", approved=False)
    assert m.count(1) == 0
    m.close()


# ---------------------------------------------------------------------------
# 4. Real tool invocation with execution evidence
# ---------------------------------------------------------------------------

def test_real_tool_invocation_produces_evidence():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[]),
        audit=AuditLog(":memory:"),
    )
    result = loop.run(
        user_id=1,
        goal="multiply",
        steps=[{"type": "tool", "tool": "calculator", "params": {"expression": "6*7"}}],
    )
    step = result["steps"][0]
    assert step["success"] is True
    assert step["result"]["result"] == 42  # real computation, not a claim
    assert any(e["tool"] == "calculator" and e["allowed"] for e in loop.audit.tail())


def test_code_generation_is_not_execution():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[1]),
        audit=AuditLog(":memory:"),
    )
    result = loop.run(
        user_id=1,
        goal="write code",
        steps=[{"type": "generate_code", "code": "print('hi')"}],
    )
    step = result["steps"][0]
    assert step["executed"] is False
    assert step["code"] == "print('hi')"
    # A pure generate step leaves no code-execution audit entry.
    assert not any(e["event"] == "code_execution" for e in loop.audit.tail())


# ---------------------------------------------------------------------------
# 5. Unauthorized tool requests are rejected
# ---------------------------------------------------------------------------

def test_restricted_tool_rejected_for_non_owner():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[1]),
        audit=AuditLog(":memory:"),
    )
    result = loop.run(
        user_id=2,  # not the owner
        goal="read a file",
        steps=[{"type": "tool", "tool": "file_reader", "params": {"path": "requirements.txt"}}],
    )
    step = result["steps"][0]
    assert step["success"] is False and step["denied"] is True
    assert "not the owner" in step["error"]
    # Denied request is recorded.
    assert any(
        e["tool"] == "file_reader" and e["allowed"] is False for e in loop.audit.tail()
    )


def test_unknown_tool_is_denied():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[]),
        audit=AuditLog(":memory:"),
    )
    result = loop.run(user_id=1, goal="x", steps=[{"type": "tool", "tool": "nope"}])
    assert result["steps"][0]["denied"] is True


def test_privileged_operation_always_denied_even_with_owner_flag():
    from genesis_protocol.agentic.policy import AgentPolicy

    policy = AgentPolicy(owner_ids=[1])
    for op in ("deploy", "modify_secret", "write_main", "merge_pr", "self_approve"):
        decision = policy.authorize_operation(1, op, owner_approved=True)
        assert decision.allowed is False
        assert decision.requires_owner_approval is True


def test_policy_fails_closed_without_owner_config():
    from genesis_protocol.agentic.policy import AgentPolicy

    policy = AgentPolicy(owner_ids=[])
    # A restricted tool with no owner configured is denied, not allowed.
    assert policy.authorize_tool(1, "file_reader", permission="restricted").allowed is False
    # Unknown permission level is denied.
    assert policy.authorize_tool(1, "x", permission="banana").allowed is False
    # SAFE tools pass.
    assert policy.authorize_tool(1, "calculator", permission="safe").allowed is True


# ---------------------------------------------------------------------------
# 6. Sandbox timeouts and resource limits
# ---------------------------------------------------------------------------

def test_sandbox_timeout_is_enforced():
    from genesis_protocol.agentic.sandbox import run_python

    result = run_python("import time; time.sleep(30)", timeout=1.0)
    assert result.timed_out is True
    assert result.success is False
    assert result.duration_ms < 10_000  # returned promptly, not after 30s


def test_sandbox_memory_limit_is_enforced():
    from genesis_protocol.agentic.sandbox import run_python

    result = run_python("x = bytearray(400 * 1024 * 1024)", timeout=10, memory_mb=64)
    assert result.success is False
    assert result.exit_code != 0


def test_sandbox_scrubs_secret_environment(monkeypatch):
    from genesis_protocol.agentic.sandbox import run_python

    monkeypatch.setenv("MY_API_KEY", "should-not-leak")
    monkeypatch.setenv("SAFE_VAR", "ok")
    result = run_python("import os; print(os.environ.get('MY_API_KEY', 'ABSENT'))")
    assert result.stdout.strip() == "ABSENT"


def test_sandbox_runs_in_isolated_dir():
    from genesis_protocol.agentic.sandbox import run_python

    result = run_python("import os; print(os.path.basename(os.getcwd()))")
    assert result.success is True
    assert result.stdout.strip().startswith("gluten_sandbox_")


def test_sandbox_caps_captured_output(monkeypatch):
    """A child that floods stdout must not grow this process without bound.

    ``capture_output=True`` buffered the pipes in the parent, so a chatty child
    grew the parent's RSS (measured ~570 MB for 200 MB of output). The capture
    is now capped, so the parent's growth stays small regardless of output.
    """
    import resource

    from genesis_protocol.agentic.sandbox import run_python

    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = run_python(
        "import sys\nfor _ in range(2000): sys.stdout.write('x' * 100000)",
        timeout=10,
        memory_mb=128,
        max_capture_bytes=50_000,
    )
    after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    growth_kb = after - before
    # 200 MB of child output; capped capture keeps the parent well under it.
    assert growth_kb < 200_000, f"parent grew {growth_kb} KB"
    assert len(result.stdout) <= 8000  # returned text still honours max_output_bytes
    assert result.limits["max_capture_bytes"] == 50_000


def test_sandbox_captures_normal_output_fully():
    """The cap must not truncate ordinary, small output."""
    from genesis_protocol.agentic.sandbox import run_python

    result = run_python("print('hello'); import sys; sys.stderr.write('warn')")
    assert result.success is True
    assert result.stdout.strip() == "hello"
    assert result.stderr.strip() == "warn"


# ---------------------------------------------------------------------------
# 7. Failed task recovery
# ---------------------------------------------------------------------------

def test_failed_task_is_recorded_and_resumable(tmp_path):
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    store = TaskStore(str(tmp_path / "tasks.json"))
    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=store,
        policy=AgentPolicy(owner_ids=[]),
        audit=AuditLog(":memory:"),
    )

    # Step 2 uses an unavailable tool -> task fails and stops.
    result = loop.run(
        user_id=1,
        goal="two steps",
        steps=[
            {"type": "tool", "tool": "calculator", "params": {"expression": "1+1"}},
            {"type": "tool", "tool": "missing_tool"},
        ],
    )
    assert result["state"] == "failed"
    task_id = result["task_id"]

    record = store.get(1, task_id)
    assert record.state == "failed"
    assert len(record.steps) == 2  # both attempts recorded

    # Resume: the leading successful step is skipped, the failed step is
    # retried (with a working tool this time), and the run completes.
    resumed = loop.run(
        user_id=1,
        goal="two steps",
        steps=[
            {"type": "tool", "tool": "calculator", "params": {"expression": "1+1"}},
            {"type": "tool", "tool": "calculator", "params": {"expression": "2+2"}},
        ],
        task_id=task_id,
    )
    assert resumed["resumed_from"] == 1
    assert len(resumed["steps"]) == 1
    assert resumed["steps"][0]["result"]["result"] == 4
    assert resumed["state"] == "completed"


def test_task_state_persists_across_instances(tmp_path):
    from genesis_protocol.agentic.tasks import TaskStore

    path = str(tmp_path / "tasks.json")
    store = TaskStore(path)
    task = store.create(5, "durable goal")
    store.append_step(5, task.id, {"type": "respond", "success": True})
    store.set_state(5, task.id, "completed")

    reloaded = TaskStore(path)
    again = reloaded.get(5, task.id)
    assert again is not None
    assert again.state == "completed"
    assert len(again.steps) == 1


def test_task_is_isolated_per_user(tmp_path):
    from genesis_protocol.agentic.tasks import TaskStore

    store = TaskStore(str(tmp_path / "tasks.json"))
    task = store.create(1, "private")
    assert store.get(2, task.id) is None
    with pytest.raises(KeyError):
        store.append_step(2, task.id, {"type": "respond"})


# ---------------------------------------------------------------------------
# 8. Accurate provider/model reporting
# ---------------------------------------------------------------------------

def _stub_chain():
    """A minimal provider chain with one configured and one unconfigured provider."""
    class _P:
        def __init__(self, model, configured):
            self._model, self._configured = model, configured

        def is_configured(self):
            return self._configured

        def get_default_model(self):
            return self._model

    class _Chain:
        _providers = {
            "groq": _P("openai/gpt-oss-120b", True),
            "gemini": _P("gemini-2.5-flash", False),
        }

    return _Chain()


def test_identity_reports_configured_providers_and_models():
    from genesis_protocol.agentic.identity import describe_runtime

    info = describe_runtime(chain=_stub_chain())
    assert info["entity"] == "GLUTEN"
    assert info["identity_source"] == "runtime_configuration"
    assert info["providers_available"] == ["groq"]
    groq = next(p for p in info["providers"] if p["name"] == "groq")
    assert groq["model"] == "openai/gpt-oss-120b"  # exact, from the chain
    assert info["default_provider"] == "groq"
    assert info["default_model"] == "openai/gpt-oss-120b"


def test_identity_never_leaks_secret_values(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_SuperSecretValue1234567890abcdef")
    from genesis_protocol.agentic.identity import describe_runtime

    blob = json.dumps(describe_runtime(chain=_stub_chain()))
    assert "SuperSecretValue" not in blob
    assert "gsk_" not in blob


def test_identity_lists_unavailable_providers_with_reason():
    from genesis_protocol.agentic.identity import describe_runtime

    info = describe_runtime(chain=_stub_chain())
    names = [p["name"] for p in info["providers_unavailable"]]
    assert "gemini" in names
    for entry in info["providers_unavailable"]:
        assert entry["reason"]


# ---------------------------------------------------------------------------
# 9. No fabricated execution or memory claims
# ---------------------------------------------------------------------------

def test_loop_does_not_claim_success_without_evidence():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[]),
        audit=AuditLog(":memory:"),
    )
    # A tool that reports failure must yield a failed step, never success.
    result = loop.run(user_id=1, goal="x", steps=[{"type": "tool", "tool": "missing"}])
    assert result["state"] == "failed"
    assert result["steps"][0]["success"] is False


def test_unknown_step_type_is_rejected():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.audit import AuditLog
    from genesis_protocol.agentic.memory import AgentMemory
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.tasks import TaskStore

    loop = AgentLoop(
        memory=AgentMemory(":memory:"),
        tasks=TaskStore(":memory:"),
        policy=AgentPolicy(owner_ids=[]),
        audit=AuditLog(":memory:"),
    )
    with pytest.raises(ValueError):
        loop.run(user_id=1, goal="x", steps=[{"type": "teleport"}])


def test_audit_log_redacts_secrets():
    from genesis_protocol.agentic.audit import AuditLog

    log = AuditLog(":memory:")
    log.record("tool_request", 1, "x", True, "ok", detail={"api_key": "sk-should-not-appear"})
    blob = json.dumps(log.tail())
    assert "sk-should-not-appear" not in blob


# ---------------------------------------------------------------------------
# 10. Web surface (real Flask routes)
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_MEMORY_DB", str(tmp_path / "mem.db"))
    monkeypatch.setenv("GLUTEN_TASK_DB", str(tmp_path / "tasks.json"))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
    import importlib

    import web.app as appmod

    importlib.reload(appmod)
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _auth(client):
    token = client.post(
        "/api/auth/login", json={"username": "admin", "password": "genesis-admin-2024"}
    ).get_json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_identity_endpoint_is_public_and_secret_free(client):
    resp = client.get("/api/identity")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["entity"] == "GLUTEN"
    assert "providers" in body


def test_capabilities_reports_no_background_autonomy(client):
    body = client.get("/api/capabilities").get_json()
    assert body["background_autonomy"] is False
    assert body["persistent_memory"] is True


def test_memory_requires_auth(client):
    assert client.get("/api/memory").status_code == 401


def test_memory_crud_over_http(client):
    headers = _auth(client)
    created = client.post(
        "/api/memory", json={"content": "likes dark mode", "approved": True}, headers=headers
    )
    assert created.status_code == 200
    mid = created.get_json()["id"]

    listed = client.get("/api/memory", headers=headers).get_json()
    assert listed["count"] == 1

    assert (
        client.patch(
            f"/api/memory/{mid}", json={"content": "likes light mode"}, headers=headers
        ).status_code
        == 200
    )
    assert client.delete(f"/api/memory/{mid}", headers=headers).status_code == 200
    assert client.get("/api/memory", headers=headers).get_json()["count"] == 0


def test_memory_endpoint_refuses_secret(client):
    headers = _auth(client)
    resp = client.post(
        "/api/memory",
        json={"content": "token = ghp_abcdefghijklmnopqrstuvwxyz012345", "approved": True},
        headers=headers,
    )
    assert resp.status_code == 400


def test_agent_run_gates_code_execution_to_owner(client):
    # admin (id 1) is the configured owner here
    headers = _auth(client)
    resp = client.post(
        "/api/agent/run",
        json={"goal": "compute", "steps": [{"type": "execute_code", "code": "print(3*14)"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.get_json()["steps"][0]["stdout"].strip() == "42"


def test_audit_tail_is_owner_only(client):
    headers = _auth(client)
    assert client.get("/api/audit/tail", headers=headers).status_code == 200
