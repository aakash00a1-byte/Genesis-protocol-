"""Regression tests for public-user hardening.

Covers the fixes made before opening registration to the public:

* memory search must not leak across users (IDOR),
* the agent loop must ignore a caller-supplied ``user_id``,
* plans are capped so one request cannot occupy a worker,
* registration input is validated and auth routes are rate limited.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def isolated_memory(tmp_path, monkeypatch):
    """A fresh long-term memory store, isolated from the default one."""
    import genesis_protocol.memory.long_term_memory as ltm_mod

    store = ltm_mod.LongTermMemory(persist_path=str(tmp_path / "chroma_db"))
    # memory_search resolves the module-level singleton, so point it at ours.
    monkeypatch.setattr(ltm_mod, "_long_term_memory", store, raising=False)
    return store


@pytest.fixture
def isolated_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test")
    monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
    monkeypatch.setenv("GENESIS_DB", str(tmp_path / "app.db"))
    monkeypatch.setenv("GLUTEN_MEMORY_DB", str(tmp_path / "mem.db"))
    monkeypatch.setenv("GLUTEN_TASK_DB", str(tmp_path / "tasks.json"))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))

    import importlib

    import genesis_protocol.agentic.agent_loop as loop_mod

    importlib.reload(loop_mod)
    return loop_mod.AgentLoop()


# -- memory search must be per-user (IDOR) ------------------------------------


def test_search_requires_user_id(isolated_memory):
    isolated_memory.add_memory("owner private: PROJECT_FALCON", user_id=1)
    for bad in (None, 0):
        with pytest.raises(ValueError):
            isolated_memory.search("PROJECT_FALCON", user_id=bad)


def test_search_returns_only_the_requested_user(isolated_memory):
    isolated_memory.add_memory("owner private: PROJECT_FALCON", user_id=1)
    isolated_memory.add_memory("user 42 note: buy milk", user_id=42)

    owner = [m.content for m in isolated_memory.search("PROJECT_FALCON", user_id=1)]
    other = [m.content for m in isolated_memory.search("PROJECT_FALCON", user_id=42)]
    assert "owner private: PROJECT_FALCON" in owner
    assert "user 42 note: buy milk" not in owner
    assert "owner private: PROJECT_FALCON" not in other


def test_memory_search_tool_is_importable():
    """The tool previously raised ImportError on get_long_term_memory."""
    from genesis_protocol.memory import get_long_term_memory

    assert callable(get_long_term_memory)


# -- agent loop binds tools to the authenticated user -------------------------


def test_agent_loop_ignores_caller_supplied_user_id(isolated_memory, isolated_loop):
    isolated_memory.add_memory("owner private: PROJECT_FALCON", user_id=1)

    # A non-owner asks for the owner's memories by passing user_id=1.
    result = isolated_loop.run(
        user_id=999,
        goal="search",
        steps=[
            {
                "type": "tool",
                "tool": "memory_search",
                "params": {"query": "PROJECT_FALCON", "user_id": 1},
            }
        ],
    )
    memories = result["steps"][0]["result"].get("memories", [])
    assert memories == []


def test_agent_loop_keeps_own_data_when_spoofing(isolated_memory, isolated_loop):
    isolated_memory.add_memory("owner private: PROJECT_FALCON", user_id=1)

    # The real owner spoofs a different id; the server-side id must win.
    result = isolated_loop.run(
        user_id=1,
        goal="search",
        steps=[
            {
                "type": "tool",
                "tool": "memory_search",
                "params": {"query": "PROJECT_FALCON", "user_id": 999},
            }
        ],
    )
    memories = result["steps"][0]["result"].get("memories", [])
    assert any("FALCON" in m["content"] for m in memories)


# -- plan is bounded ----------------------------------------------------------


def test_plan_rejects_too_many_steps(isolated_loop):
    import genesis_protocol.agentic.agent_loop as loop_mod

    steps = [{"type": "respond", "goal": "x"}] * (loop_mod.MAX_STEPS + 1)
    with pytest.raises(ValueError):
        isolated_loop.run(user_id=1, goal="x", steps=steps)


def test_plan_accepts_at_the_limit(isolated_loop):
    import genesis_protocol.agentic.agent_loop as loop_mod

    steps = [{"type": "respond", "goal": "x"}] * loop_mod.MAX_STEPS
    result = isolated_loop.run(user_id=1, goal="x", steps=steps)
    assert len(result["steps"]) == loop_mod.MAX_STEPS


# -- registration validation --------------------------------------------------


@pytest.mark.parametrize(
    "username,email,password",
    [
        ("ab", "u@example.com", "longenough1"),  # username too short
        ("bad name", "u@example.com", "longenough1"),  # space
        ("user!", "u@example.com", "longenough1"),  # bad char
        ("validuser", "not-an-email", "longenough1"),  # bad email
        ("validuser", "u@example.com", "short"),  # password too short
    ],
)
def test_validate_registration_rejects_bad_input(username, email, password):
    from web.app import validate_registration

    assert validate_registration(username, email, password) is not None


def test_validate_registration_accepts_good_input():
    from web.app import validate_registration

    assert validate_registration("good_user-1", "a@b.co", "longenough1") is None


@pytest.fixture
def client():
    from web.app import app

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_register_endpoint_rejects_bad_email(client):
    r = client.post(
        "/api/auth/register",
        json={"username": "validuser", "email": "nope", "password": "longenough1"},
    )
    assert r.status_code == 400


def test_register_endpoint_rejects_bad_username(client):
    r = client.post(
        "/api/auth/register",
        json={"username": "bad user", "email": "u@example.com", "password": "longenough1"},
    )
    assert r.status_code == 400


# -- rate limiter has a working fallback --------------------------------------


def test_rate_limiter_backend_is_reported():
    from web.app import RATE_LIMITER_BACKEND

    assert RATE_LIMITER_BACKEND in {"flask-limiter", "in-process"}


def test_in_process_rate_limiter_blocks_after_limit():
    """The fallback must actually limit; a no-op once hid a dead limiter."""
    from web.app import app, _MemoryRateLimiter

    rl = _MemoryRateLimiter()

    @rl.limit("2 per minute")
    def view():
        return "ok"

    app.config["TESTING"] = False
    try:
        with app.test_request_context("/x", environ_base={"REMOTE_ADDR": "1.2.3.4"}):
            assert view() == "ok"
            assert view() == "ok"
            blocked = view()
            if isinstance(blocked, tuple):
                blocked = app.make_response(blocked)
            assert blocked.status_code == 429
    finally:
        app.config["TESTING"] = True


def test_rate_limit_keys_on_forwarded_client_ip(client):
    """Behind a proxy the socket peer rotates; the limiter must key on the
    forwarded client address or every request lands in a fresh bucket."""
    from web.app import app

    app.config["TESTING"] = False
    try:
        codes = [
            client.post(
                "/api/auth/login",
                headers={"X-Forwarded-For": "203.0.113.99"},
                environ_base={"REMOTE_ADDR": f"10.0.0.{i % 7}"},
                json={"username": "nobody", "password": "wrongpass1"},
            ).status_code
            for i in range(13)
        ]
    finally:
        app.config["TESTING"] = True
    assert 429 in codes, codes
