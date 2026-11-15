"""Secure agent coordination (V7 P7).

Covers the P7 contract:

* shared identity and capability registry (derived from the canonical systems)
* capability manifests and least-privilege delegation (child grant is a subset)
* authenticated, tamper-evident agent-to-agent messages
* task ownership, duplicate prevention, conflict resolution
* coordination across multiple agents without privilege escalation
* privacy of shared context (clearance filtering + secret redaction)
* bounded, documented provider/model fallback
* consistent authorization across Telegram, GitHub, web and Gluten
* a hard rule that no agent may grant itself or another agent privileges

Hermetic: in-memory identity registry, credential store and audit log.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from genesis_protocol.agentic.audit import AuditLog  # noqa: E402
from genesis_protocol.agentic.credentials import CredentialStore  # noqa: E402
from genesis_protocol.agentic.identity_registry import IdentityRegistry  # noqa: E402
from genesis_protocol.agentic.policy import AgentPolicy  # noqa: E402
from genesis_protocol.coordination import (  # noqa: E402
    CapabilityRegistry,
    CoordinationError,
    CoordinationManager,
    Envelope,
    InterfaceAuthorizer,
    MessageBus,
    MessageError,
    SharedContext,
    TaskCoordinator,
)


@pytest.fixture()
def env():
    audit = AuditLog(":memory:")
    creds = CredentialStore(":memory:")
    ids = IdentityRegistry(path=":memory:", credentials=creds, audit=audit)
    policy = AgentPolicy(owner_ids={1})
    registry = CapabilityRegistry(identities=ids, policy=policy)
    return {"ids": ids, "creds": creds, "policy": policy, "registry": registry}


def _register(env, name, role, tools, parent_id=None, owner_id=1):
    return env["ids"].register(name=name, role=role, owner_id=owner_id, tools=tools,
                               parent_id=parent_id, owner_approved=True)


def _envelope(sender, recipient, mtype="task.assign", payload=None, nonce="n1"):
    return Envelope(sender=sender, recipient=recipient, message_type=mtype,
                    payload=payload if payload is not None else {"task_id": "TASK-1"},
                    nonce=nonce, sent_at=datetime.now(timezone.utc).isoformat())


def _copy(env):
    d = env.to_dict()
    return Envelope(**{
        k: d[k] for k in ("sender", "recipient", "message_type", "payload",
                          "nonce", "sent_at", "signature")
    })


# ---------------------------------------------------------------------------
# 1. Registry + manifests
# ---------------------------------------------------------------------------

class TestCapabilityRegistry:
    def test_manifest_derived_from_identity(self, env):
        a = _register(env, "coord", "coordinator", ["calculator", "web_search"])
        m = env["registry"].manifest(a.agent_id)
        assert m.role == "coordinator" and set(m.tools) == {"calculator", "web_search"}

    def test_manifest_only_contains_known_tools(self, env):
        # The identity registry already refuses unknown tools at registration, so
        # the manifest can only ever name tools that exist.
        with pytest.raises(Exception):
            _register(env, "coord", "coordinator", ["calculator", "not_a_real_tool"])
        a = _register(env, "coord2", "coordinator", ["calculator"])
        m = env["registry"].manifest(a.agent_id)
        assert set(m.tools).issubset(env["registry"].known_tools())

    def test_unknown_agent_has_no_manifest(self, env):
        assert env["registry"].manifest("agt_000000000000") is None

    def test_depth_and_parent_tracked(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        m = env["registry"].manifest(c.agent_id)
        assert m.parent_id == p.agent_id and m.depth == 1

    def test_can_use_requires_grant(self, env):
        p = _register(env, "p", "coordinator", ["calculator", "web_search"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        assert env["registry"].can_use(c.agent_id, "calculator") is True
        assert env["registry"].can_use(c.agent_id, "web_search") is False

    def test_can_use_fails_for_non_active(self, env):
        c = _register(env, "c", "worker", ["calculator"])
        env["ids"].suspend(c.agent_id, owner_approved=True)
        assert env["registry"].can_use(c.agent_id, "calculator") is False

    def test_is_subset(self):
        assert CapabilityRegistry.is_subset(["a"], ["a", "b"]) is True
        assert CapabilityRegistry.is_subset(["a", "c"], ["a", "b"]) is False


# ---------------------------------------------------------------------------
# 2. Messaging security
# ---------------------------------------------------------------------------

class TestMessaging:
    def _bus(self, env):
        return MessageBus(identities=env["ids"], credentials=env["creds"])

    def test_signed_message_round_trips(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        bus = self._bus(env)
        sent = bus.send(_envelope(p.agent_id, "x"), tok)
        assert sent.signature
        assert bus.receive(_copy(sent), tok).validated is True

    def test_replay_is_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        bus = self._bus(env)
        sent = bus.send(_envelope(p.agent_id, "x", nonce="dup"), tok)
        bus.receive(_copy(sent), tok)
        with pytest.raises(MessageError):
            bus.receive(_copy(sent), tok)

    def test_tampering_is_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        bus = self._bus(env)
        sent = bus.send(_envelope(p.agent_id, "x"), tok)
        sent.payload["task_id"] = "EVIL"
        with pytest.raises(MessageError):
            bus.receive(sent, tok)

    def test_unknown_message_type_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        with pytest.raises(MessageError):
            self._bus(env).send(_envelope(p.agent_id, "x", mtype="exfiltrate"), tok)

    def test_missing_required_field_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        with pytest.raises(MessageError):
            self._bus(env).send(_envelope(p.agent_id, "x", payload={}), tok)

    def test_unauthenticated_sender_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        o = _register(env, "o", "worker", ["calculator"])
        tok_o = env["creds"].issue(o.agent_id, ttl_seconds=60)
        with pytest.raises(MessageError):
            self._bus(env).send(_envelope(p.agent_id, "x"), tok_o)

    def test_stale_message_rejected(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=600)
        bus = self._bus(env)
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        envl = _envelope(p.agent_id, "x")
        envl.sent_at = old.isoformat()
        bus.send(envl, tok)
        with pytest.raises(MessageError):
            bus.receive(envl, tok)

    def test_provenance_is_ordered(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        tok = env["creds"].issue(p.agent_id, ttl_seconds=60)
        bus = self._bus(env)
        bus.send(_envelope(p.agent_id, "x", nonce="a", payload={"task_id": "T1"}), tok)
        chain = bus.provenance("T1")
        assert chain and chain[0]["payload"]["task_id"] == "T1"


# ---------------------------------------------------------------------------
# 3. Task ownership, dedup, conflicts
# ---------------------------------------------------------------------------

class TestTaskCoordination:
    def test_idempotent_assignment(self, env):
        tc = TaskCoordinator(registry=env["registry"])
        a = tc.assign("agent-1", "key-1")
        b = tc.assign("agent-1", "key-1")
        assert a.task_id == b.task_id

    def test_single_owner(self, env):
        tc = TaskCoordinator(registry=env["registry"])
        tc.assign("agent-1", "key-1")
        tc.assign("agent-2", "key-1")
        assert tc.owner_of("TASK-00001") == "agent-1"
        assert len(tc.conflicts()) == 1
        assert tc.conflicts()[0]["winner"] == "agent-1"

    def test_delegation_to_subset_is_allowed(self, env):
        p = _register(env, "p", "coordinator", ["calculator", "web_search"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        tc = TaskCoordinator(registry=env["registry"])
        t = tc.assign(p.agent_id, "k")
        d = tc.delegate(t.task_id, p.agent_id, c.agent_id)
        assert d.owner == c.agent_id and d.delegated_from == p.agent_id

    def test_delegation_outside_grant_blocked(self, env):
        # The identity registry refuses to even create a child whose grant exceeds
        # its parent's, so the escalation cannot arise. We assert that guard, then
        # confirm the coordinator refuses a handoff to a non-subset agent.
        p = _register(env, "p", "coordinator", ["calculator"])
        with pytest.raises(Exception):
            _register(env, "c", "worker", ["calculator", "web_search"], parent_id=p.agent_id)
        # A sibling with a wider grant than the delegator must also be refused.
        c2 = _register(env, "c2", "worker", ["calculator", "web_search"])
        tc = TaskCoordinator(registry=env["registry"])
        t = tc.assign(p.agent_id, "k")
        with pytest.raises(CoordinationError):
            tc.delegate(t.task_id, p.agent_id, c2.agent_id)

    def test_non_owner_cannot_delegate(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        tc = TaskCoordinator(registry=env["registry"])
        t = tc.assign(p.agent_id, "k")
        with pytest.raises(CoordinationError):
            tc.delegate(t.task_id, c.agent_id, p.agent_id)

    def test_worker_role_cannot_delegate(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        tc = TaskCoordinator(registry=env["registry"])
        t = tc.assign(c.agent_id, "k")
        with pytest.raises(CoordinationError):
            tc.delegate(t.task_id, c.agent_id, p.agent_id)

    def test_state_update_requires_owner(self, env):
        tc = TaskCoordinator(registry=env["registry"])
        t = tc.assign("agent-1", "k")
        with pytest.raises(CoordinationError):
            tc.update_state(t.task_id, "agent-2", "completed")
        assert tc.update_state(t.task_id, "agent-1", "completed").state == "completed"


# ---------------------------------------------------------------------------
# 4. Shared context privacy
# ---------------------------------------------------------------------------

class TestSharedContext:
    def test_clearance_filters_private(self):
        ctx = SharedContext()
        ctx.put("T", "goal", "fix", "owner", "internal")
        ctx.put("T", "secret_plan", "x", "owner", "private")
        view = ctx.view("T", "worker", "worker-1")
        assert "goal" in view["context"] and "secret_plan" in view["redacted_keys"]

    def test_owner_sees_private(self):
        ctx = SharedContext()
        ctx.put("T", "plan", "x", "owner", "private")
        view = ctx.view("T", "manager", "owner", owner="owner")
        assert view["context"].get("plan") == "x"

    def test_secrets_are_redacted_before_sharing(self):
        ctx = SharedContext()
        ctx.put("T", "token", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "owner", "internal")
        view = ctx.view("T", "manager", "owner", owner="owner")
        assert "ghp_" not in str(view["context"])

    def test_unknown_sensitivity_is_treated_private(self):
        ctx = SharedContext()
        ctx.put("T", "k", "v", "owner", "cosmic")
        assert ctx.view("T", "viewer", "viewer-1")["context"] == {}

    def test_unknown_role_gets_public_clearance(self):
        ctx = SharedContext()
        ctx.put("T", "k", "v", "owner", "internal")
        assert ctx.view("T", "stranger", "s")["context"] == {}


# ---------------------------------------------------------------------------
# 5. Provider / model tracking
# ---------------------------------------------------------------------------

class TestProviderTracking:
    def test_fallback_detected(self, env):
        reg = env["registry"]
        reg.record_provider("agent-1", "openai", "gpt")
        rec = reg.record_provider("agent-1", "groq", "llama")
        assert rec.fallback is True
        assert reg.provider_status()["total_fallbacks"] == 1

    def test_failure_counted(self, env):
        reg = env["registry"]
        reg.record_provider("agent-1", "openai", "gpt", ok=False)
        assert reg.provider_status()["total_failures"] == 1


# ---------------------------------------------------------------------------
# 6. Cross-interface consistency
# ---------------------------------------------------------------------------

class TestInterfaceAuthorization:
    def test_owner_allowed_same_everywhere(self, env):
        auth = InterfaceAuthorizer(policy=env["policy"], registry=env["registry"])
        for iface in ("telegram", "web", "api"):
            assert auth.authorize_tool(iface, 1, "calculator").allowed is True

    def test_stranger_denied_same_everywhere(self, env):
        # A restricted tool is denied for a non-owner identically on every
        # interface; a safe tool is allowed for anyone (canonical policy).
        auth = InterfaceAuthorizer(policy=env["policy"], registry=env["registry"])
        for iface in ("telegram", "web", "api"):
            assert auth.authorize_tool(iface, 999, "python").allowed is False
            assert auth.authorize_tool(iface, 999, "calculator").allowed is True

    def test_unknown_interface_fails_closed(self, env):
        auth = InterfaceAuthorizer(policy=env["policy"], registry=env["registry"])
        assert auth.authorize_tool("carrier-pigeon", 1, "calculator").allowed is False

    def test_unresolved_principal_fails_closed(self, env):
        auth = InterfaceAuthorizer(policy=env["policy"], registry=env["registry"])
        assert auth.authorize_tool("web", "", "calculator").allowed is False
        assert auth.authorize_tool("web", "not-a-number", "calculator").allowed is False

    def test_agent_caller_governed_by_manifest(self, env):
        p = _register(env, "p", "coordinator", ["calculator"])
        c = _register(env, "c", "worker", ["calculator"], parent_id=p.agent_id)
        auth = InterfaceAuthorizer(policy=env["policy"], registry=env["registry"])
        assert auth.authorize_tool("web", 1, "calculator", agent_id=c.agent_id).allowed is True
        assert auth.authorize_tool("web", 1, "web_search", agent_id=c.agent_id).allowed is False

    def test_principal_resolution(self):
        assert InterfaceAuthorizer.resolve_principal("telegram", "42") == "42"
        assert InterfaceAuthorizer.resolve_principal("github", "  octocat ") == "octocat"
        assert InterfaceAuthorizer.resolve_principal("telegram", "abc") is None
        assert InterfaceAuthorizer.resolve_principal("nope", 1) is None


# ---------------------------------------------------------------------------
# 7. Hard rule: no self/other privilege escalation
# ---------------------------------------------------------------------------

class TestNoPrivilegeEscalation:
    def test_registry_has_no_grant_method(self, env):
        reg = env["registry"]
        for name in dir(reg):
            assert "grant" not in name.lower()
            assert "escalate" not in name.lower()

    def test_manager_exposes_no_grant_method(self):
        mgr = CoordinationManager()
        for name in dir(mgr):
            assert "grant" not in name.lower()
            assert "escalate" not in name.lower()

    def test_manifest_cannot_exceed_identity_grant(self, env):
        a = _register(env, "a", "worker", ["calculator"])
        m = env["registry"].manifest(a.agent_id)
        assert set(m.tools).issubset(set(a.tools))

    def test_manager_status_serialisable(self, env):
        import json

        mgr = CoordinationManager(registry=env["registry"])
        json.dumps(mgr.status())
