"""Agent identity, permission boundaries, credentials and trust (V7 P2).

These tests hold the identity/trust contract introduced in V7 P2 and drive the
adversarial cases the design must refuse:

* spoofed / unknown identity
* privilege escalation through a child grant
* a forged parent (over-privileged child, or a non-existent parent)
* expired / exhausted / revoked credentials
* unauthorized tool access outside an agent's grant
* self-granted privilege (no owner approval)
* privileged operations (deploy, merge, secret change) denied to every agent

The whole point is that identity and trust never *grant* anything: the canonical
fail-closed ``AgentPolicy`` and the canonical ``ToolRegistry`` remain the only
permission engines. An agent's grant can only narrow, never widen, that.
"""
from __future__ import annotations

import time

import pytest

from genesis_protocol.agentic.audit import AuditLog
from genesis_protocol.agentic.boundaries import BoundaryGuard
from genesis_protocol.agentic.credentials import CredentialStore
from genesis_protocol.agentic.identity_registry import (
    IdentityError,
    IdentityRegistry,
    get_identity_registry,
)
from genesis_protocol.agentic.policy import AgentPolicy
from genesis_protocol.agentic.trust import TrustEvaluator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _isolate_identity_singleton(monkeypatch):
    """Point the process-wide registry/credential/audit singletons at memory.

    The agent loop and the web endpoints resolve identity through
    ``get_identity_registry()``. Swapping the singleton keeps those tests
    hermetic - no ``data/`` files are written and identities never leak between
    tests.
    """
    import genesis_protocol.agentic.identity_registry as id_mod

    memory_registry = IdentityRegistry(
        ":memory:", credentials=CredentialStore(":memory:"), audit=AuditLog(":memory:")
    )
    monkeypatch.setattr(id_mod, "_default", memory_registry, raising=False)
    yield


def _registry(**kwargs) -> IdentityRegistry:
    """An isolated in-memory registry with its own audit + credential store."""
    return IdentityRegistry(
        ":memory:",
        credentials=CredentialStore(":memory:"),
        audit=AuditLog(":memory:"),
        **kwargs,
    )


def _owner() -> AgentPolicy:
    return AgentPolicy(owner_ids=[1])


# ---------------------------------------------------------------------------
# 1. Agent Identity Registry
# ---------------------------------------------------------------------------

class TestIdentityRegistry:
    def test_register_captures_full_identity(self):
        reg = _registry()
        a = reg.register(
            name="root", role="orchestrator", owner_id=1,
            provider="groq", model="llama-3.1", tools=["calculator"],
            owner_approved=True,
        )
        assert a.agent_id.startswith("agt_")
        assert (a.role, a.owner_id, a.provider, a.model) == ("orchestrator", 1, "groq", "llama-3.1")
        assert a.parent_id is None
        assert a.status == "active"
        assert a.tools == ("calculator",)

    def test_identity_ids_are_unique(self):
        reg = _registry()
        ids = {
            reg.register(name=f"a{i}", role="worker", owner_id=1, owner_approved=True).agent_id
            for i in range(5)
        }
        assert len(ids) == 5

    def test_duplicate_name_is_refused(self):
        reg = _registry()
        reg.register(name="dup", role="worker", owner_id=1, owner_approved=True)
        with pytest.raises(IdentityError):
            reg.register(name="dup", role="worker", owner_id=1, owner_approved=True)

    def test_unknown_tool_in_grant_is_refused(self):
        reg = _registry()
        with pytest.raises(IdentityError):
            reg.register(name="x", role="worker", owner_id=1, tools=["no_such_tool"],
                         owner_approved=True)

    def test_identity_survives_restart(self, tmp_path):
        path = str(tmp_path / "agents.json")
        reg = IdentityRegistry(path, credentials=CredentialStore(":memory:"), audit=AuditLog(":memory:"))
        a = reg.register(name="persist", role="worker", owner_id=1, owner_approved=True)
        reloaded = IdentityRegistry(path, credentials=CredentialStore(":memory:"), audit=AuditLog(":memory:"))
        assert reloaded.get(a.agent_id) is not None


# ---------------------------------------------------------------------------
# 2. Permission boundaries - least privilege, no self-granting
# ---------------------------------------------------------------------------

class TestPermissionBoundaries:
    def test_registration_requires_owner_approval(self):
        reg = _registry()
        with pytest.raises(IdentityError):
            reg.register(name="sneaky", role="worker", owner_id=1)  # no approval

    def test_grant_change_requires_owner_approval(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, tools=["calculator"],
                         owner_approved=True)
        with pytest.raises(IdentityError):
            reg.update_grants(a.agent_id, add=["file_reader"])  # no approval

    def test_child_grant_exceeding_parent_refused(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        with pytest.raises(IdentityError):
            reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                         tools=["file_reader"], owner_approved=True)

    def test_grant_update_cannot_exceed_parent(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        child = reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                             tools=["calculator"], owner_approved=True)
        with pytest.raises(IdentityError):
            reg.update_grants(child.agent_id, add=["file_reader"], owner_approved=True)

    def test_grant_can_narrow_freely(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1,
                         tools=["calculator", "file_reader"], owner_approved=True)
        updated = reg.update_grants(a.agent_id, remove=["file_reader"], owner_approved=True)
        assert updated.tools == ("calculator",)

    def test_boundary_denies_tool_outside_grant(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        a = reg.register(name="w", role="worker", owner_id=1, tools=["calculator"],
                         owner_approved=True)
        # file_reader is a real restricted tool but outside this agent's grant.
        decision = guard.check_tool(a.agent_id, "file_reader", user_id=1, owner_approved=True)
        assert decision.allowed is False
        assert "grant" in decision.reason

    def test_boundary_allows_tool_within_grant_and_policy(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        a = reg.register(name="w", role="worker", owner_id=1, tools=["calculator"],
                         owner_approved=True)
        assert guard.check_tool(a.agent_id, "calculator", user_id=1).allowed is True

    def test_empty_grant_means_no_ceiling_not_all_access(self):
        """An empty grant imposes no extra ceiling; the canonical policy still decides."""
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=AgentPolicy(owner_ids=[]))
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        # No owner configured -> restricted tool still denied by the canonical policy.
        assert guard.check_tool(a.agent_id, "file_reader", user_id=1).allowed is False


# ---------------------------------------------------------------------------
# 3. Identity verification before privileged actions
# ---------------------------------------------------------------------------

class TestIdentityVerification:
    def test_unknown_agent_fails_verification(self):
        reg = _registry()
        assert reg.verify("agt_deadbeef0000").ok is False

    def test_missing_agent_id_fails_verification(self):
        reg = _registry()
        assert reg.verify(None).ok is False
        assert reg.verify("").ok is False

    def test_active_agent_verifies(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        assert reg.verify(a.agent_id).ok is True

    def test_suspended_agent_fails_verification(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        reg.suspend(a.agent_id, owner_approved=True)
        assert reg.verify(a.agent_id).ok is False

    def test_privileged_operation_denied_even_for_verified_agent(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        for op in ("deploy", "merge_pr", "modify_secret", "write_main", "self_approve"):
            assert guard.check_operation(a.agent_id, op, user_id=1).allowed is False


# ---------------------------------------------------------------------------
# 4. Credential safety - short-lived, hash-only, never exposed
# ---------------------------------------------------------------------------

class TestCredentialSafety:
    def test_issued_credential_verifies_once(self):
        store = CredentialStore(":memory:")
        token = store.issue("agt_000000000000", ttl_seconds=60, max_uses=1)
        assert store.verify(token).ok is True
        # single-use: the second verification fails
        assert store.verify(token).ok is False

    def test_credential_stores_only_a_hash(self):
        store = CredentialStore(":memory:")
        token = store.issue("agt_000000000000", ttl_seconds=60)
        listed = store.list_for_agent("agt_000000000000")
        assert listed, "credential should be listed"
        serialised = str(listed)
        assert token not in serialised, "raw token must never be stored or listed"
        assert "hash_prefix" in listed[0]

    def test_expired_credential_fails(self):
        store = CredentialStore(":memory:")
        token = store.issue("agt_000000000000", ttl_seconds=1)
        time.sleep(1.1)
        assert store.verify(token).ok is False

    def test_revoked_credential_fails(self):
        store = CredentialStore(":memory:")
        token = store.issue("agt_000000000000", ttl_seconds=60)
        store.revoke_for_agent("agt_000000000000")
        assert store.verify(token).ok is False

    def test_exhausted_credential_fails(self):
        store = CredentialStore(":memory:")
        token = store.issue("agt_000000000000", ttl_seconds=60, max_uses=2)
        assert store.verify(token).ok is True
        assert store.verify(token).ok is True
        assert store.verify(token).ok is False

    def test_ttl_must_be_bounded(self):
        store = CredentialStore(":memory:")
        with pytest.raises(ValueError):
            store.issue("agt_000000000000", ttl_seconds=0)
        with pytest.raises(ValueError):
            store.issue("agt_000000000000", ttl_seconds=10_000_000)

    def test_credential_bound_to_wrong_agent_fails_identity(self):
        reg = _registry()
        a = reg.register(name="a", role="worker", owner_id=1, owner_approved=True)
        b = reg.register(name="b", role="worker", owner_id=1, owner_approved=True)
        token_for_b = reg._credentials.issue(b.agent_id, ttl_seconds=60)
        # Presenting b's credential as a's must fail.
        result = reg.verify(a.agent_id, credential=token_for_b)
        assert result.ok is False
        assert "belong" in result.reason

    def test_verification_with_correct_credential_passes(self):
        reg = _registry()
        a = reg.register(name="a", role="worker", owner_id=1, owner_approved=True)
        token = reg._credentials.issue(a.agent_id, ttl_seconds=60)
        assert reg.verify(a.agent_id, credential=token).ok is True


# ---------------------------------------------------------------------------
# 5. Trust evaluation - evidence-based, never bypasses policy
# ---------------------------------------------------------------------------

class TestTrustEvaluation:
    def _identity(self, reg, **kw):
        return reg.register(name=kw.pop("name", "w"), role="worker", owner_id=1,
                            owner_approved=True, **kw)

    def test_new_agent_is_provisional_at_best(self):
        reg = _registry()
        a = self._identity(reg)
        report = TrustEvaluator(audit=reg.audit).evaluate(a, history=[])
        assert report.level in ("untrusted", "provisional")

    def test_revoked_identity_is_always_untrusted(self):
        reg = _registry()
        a = self._identity(reg)
        reg.revoke(a.agent_id, owner_approved=True)
        good_history = [{"event": "tool_result", "allowed": True, "agent_id": a.agent_id}] * 50
        report = TrustEvaluator(audit=reg.audit).evaluate(reg.get(a.agent_id), history=good_history)
        assert report.level == "untrusted"
        assert report.score == 0

    def test_poor_record_never_exceeds_provisional(self):
        reg = _registry()
        a = self._identity(reg)
        history = (
            [{"event": "tool_result", "allowed": True, "agent_id": a.agent_id}] * 2
            + [{"event": "tool_result", "allowed": False, "agent_id": a.agent_id}] * 5
        )
        report = TrustEvaluator(audit=reg.audit).evaluate(a, history=history)
        assert report.level in ("untrusted", "provisional")

    def test_strong_record_reaches_verified(self):
        reg = _registry()
        a = self._identity(reg)
        history = [{"event": "tool_result", "allowed": True, "agent_id": a.agent_id}] * 20
        report = TrustEvaluator(audit=reg.audit).evaluate(a, history=history)
        assert report.level == "verified"
        assert report.evidence["successes"] == 20

    def test_trust_does_not_change_policy(self):
        """A 'verified' agent still cannot reach a privileged operation."""
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        a = self._identity(reg)
        TrustEvaluator(audit=reg.audit).evaluate(
            a, history=[{"event": "tool_result", "allowed": True}] * 50
        )
        assert guard.check_operation(a.agent_id, "deploy", user_id=1).allowed is False


# ---------------------------------------------------------------------------
# 6. Audit trail - identity, action, decision and outcome
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_registration_is_audited_with_identity(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        entries = [e for e in reg.audit.tail() if e["event"] == "agent_registered"]
        assert entries and entries[-1]["agent_id"] == a.agent_id

    def test_agent_loop_records_identity_on_tool_request(self, tmp_path):
        from genesis_protocol.agentic.agent_loop import AgentLoop
        from genesis_protocol.agentic.memory import AgentMemory
        from genesis_protocol.agentic.tasks import TaskStore

        audit = AuditLog(":memory:")
        loop = AgentLoop(
            memory=AgentMemory(":memory:"),
            tasks=TaskStore(str(tmp_path / "t.json")),
            policy=_owner(),
            audit=audit,
        )
        reg = get_identity_registry()
        # Reuse the process registry but drive the loop with an explicit agent id.
        identity = reg.register(name="loop-agent", role="worker", owner_id=1,
                                tools=["calculator"], owner_approved=True)
        result = loop.run(
            user_id=1, goal="calc",
            steps=[{"type": "tool", "tool": "calculator", "params": {"expression": "2+2"}}],
            agent_id=identity.agent_id,
        )
        assert result["state"] == "completed"
        entries = [e for e in audit.tail() if e["event"] == "tool_request"]
        assert entries and entries[-1]["agent_id"] == identity.agent_id

    def test_denied_action_is_recorded_with_identity(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        a = reg.register(name="w", role="worker", owner_id=1, tools=["calculator"],
                         owner_approved=True)
        decision = guard.check_tool(a.agent_id, "file_reader", user_id=1)
        assert decision.allowed is False
        assert decision.agent_id == a.agent_id
        assert decision.tool == "file_reader"


# ---------------------------------------------------------------------------
# 7. Revocation
# ---------------------------------------------------------------------------

class TestRevocation:
    def test_revoked_agent_fails_verification(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        reg.revoke(a.agent_id, owner_approved=True)
        assert reg.verify(a.agent_id).ok is False

    def test_revocation_requires_owner_approval(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        with pytest.raises(IdentityError):
            reg.revoke(a.agent_id)  # no approval

    def test_revocation_cascades_to_descendants(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        child = reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                             tools=["calculator"], owner_approved=True)
        revoked = reg.revoke(parent.agent_id, owner_approved=True)
        assert {r.agent_id for r in revoked} == {parent.agent_id, child.agent_id}
        assert reg.verify(child.agent_id).ok is False

    def test_revocation_drops_live_credentials(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        token = reg._credentials.issue(a.agent_id, ttl_seconds=60)
        reg.revoke(a.agent_id, owner_approved=True)
        assert reg._credentials.verify(token).ok is False

    def test_revoked_agent_cannot_be_reactivated(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        reg.revoke(a.agent_id, owner_approved=True)
        with pytest.raises(IdentityError):
            reg.reactivate(a.agent_id, owner_approved=True)

    def test_suspend_then_reactivate(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        reg.suspend(a.agent_id, owner_approved=True)
        assert reg.verify(a.agent_id).ok is False
        reg.reactivate(a.agent_id, owner_approved=True)
        assert reg.verify(a.agent_id).ok is True

    def test_cannot_reactivate_child_of_revoked_ancestor(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        child = reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                             tools=["calculator"], owner_approved=True)
        reg.suspend(child.agent_id, owner_approved=True)
        reg.revoke(parent.agent_id, owner_approved=True)
        with pytest.raises(IdentityError):
            reg.reactivate(child.agent_id, owner_approved=True)


# ---------------------------------------------------------------------------
# 8. Adversarial scenarios (the headline cases)
# ---------------------------------------------------------------------------

class TestAdversarial:
    def test_spoofed_identity_is_denied(self):
        """A made-up agent id never verifies and never reaches a tool."""
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        decision = guard.check_tool("agt_ffffffffffff", "calculator", user_id=1)
        assert decision.allowed is False
        assert "not verified" in decision.reason

    def test_privilege_escalation_via_child_grant_is_denied(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        with pytest.raises(IdentityError):
            reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                         tools=["file_reader"], owner_approved=True)

    def test_forged_parent_is_denied(self):
        """A child cannot name a parent that does not exist."""
        reg = _registry()
        with pytest.raises(IdentityError):
            reg.register(name="c", role="worker", owner_id=1, parent_id="agt_000000000000",
                         tools=["calculator"], owner_approved=True)

    def test_child_of_suspended_parent_is_denied(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        reg.suspend(parent.agent_id, owner_approved=True)
        with pytest.raises(IdentityError):
            reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                         tools=["calculator"], owner_approved=True)

    def test_expired_credential_cannot_authorize(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        token = reg._credentials.issue(a.agent_id, ttl_seconds=1)
        time.sleep(1.1)
        assert reg.verify(a.agent_id, credential=token).ok is False

    def test_unauthorized_tool_access_is_denied(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=AgentPolicy(owner_ids=[]))
        a = reg.register(name="w", role="worker", owner_id=1, tools=["file_reader"],
                         owner_approved=True)
        # Grant includes file_reader, but no owner is configured -> policy denies.
        assert guard.check_tool(a.agent_id, "file_reader", user_id=1).allowed is False

    def test_self_granted_privilege_is_denied(self):
        """Nothing in the identity layer lets an agent widen its own grant."""
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, tools=["calculator"],
                         owner_approved=True)
        with pytest.raises(IdentityError):
            reg.update_grants(a.agent_id, add=["file_reader"], owner_approved=False)

    def test_agent_loop_refuses_unverifiable_identity(self, tmp_path):
        from genesis_protocol.agentic.agent_loop import AgentLoop
        from genesis_protocol.agentic.memory import AgentMemory
        from genesis_protocol.agentic.tasks import TaskStore

        loop = AgentLoop(
            memory=AgentMemory(":memory:"),
            tasks=TaskStore(str(tmp_path / "t.json")),
            policy=_owner(),
            audit=AuditLog(":memory:"),
        )
        result = loop.run(
            user_id=1, goal="x",
            steps=[{"type": "tool", "tool": "calculator", "params": {"expression": "1+1"}}],
            agent_id="agt_ffffffffffff",
        )
        assert result["state"] == "denied"
        assert result["steps"] == []
        denied = [e for e in loop.audit.tail() if e["event"] == "identity_denied"]
        assert denied

    def test_agent_loop_denies_tool_outside_grant(self, tmp_path):
        from genesis_protocol.agentic.agent_loop import AgentLoop
        from genesis_protocol.agentic.memory import AgentMemory
        from genesis_protocol.agentic.tasks import TaskStore

        loop = AgentLoop(
            memory=AgentMemory(":memory:"),
            tasks=TaskStore(str(tmp_path / "t.json")),
            policy=_owner(),
            audit=AuditLog(":memory:"),
        )
        identity = get_identity_registry().register(
            name="grant-limited", role="worker", owner_id=1, tools=["calculator"],
            owner_approved=True,
        )
        result = loop.run(
            user_id=1, goal="read",
            steps=[{"type": "tool", "tool": "file_reader", "params": {"path": "README.md"}}],
            agent_id=identity.agent_id,
        )
        step = result["steps"][0]
        assert step["denied"] is True
        assert "grant" in step["error"]


# ---------------------------------------------------------------------------
# Web surface: owner-only, no secret leakage
# ---------------------------------------------------------------------------

class TestIdentityWebSurface:
    @pytest.fixture
    def client(self):
        import web.app as appmod

        appmod.app.config["TESTING"] = True
        return appmod.app.test_client()

    def test_agents_list_requires_owner(self, client, monkeypatch):
        monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["username"] = "notowner"
        assert client.get("/api/agents").status_code == 403

    def test_agents_list_ok_for_owner(self, client, monkeypatch):
        monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "owner"
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert "agents" in resp.get_json()

    def test_agents_list_anonymous_is_401_json(self, client):
        resp = client.get("/api/agents")
        assert resp.status_code == 401
        assert resp.is_json

    def test_verify_endpoint_never_echoes_credential(self, client, monkeypatch):
        monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "owner"
        secret = "agtok_supersecrettokenvalue"
        resp = client.post("/api/agents/agt_000000000000/verify", json={"credential": secret})
        assert resp.status_code == 200
        assert secret not in resp.get_data(as_text=True)

    def test_agent_detail_requires_owner(self, client, monkeypatch):
        monkeypatch.setenv("GLUTEN_OWNER_IDS", "1")
        with client.session_transaction() as sess:
            sess["user_id"] = 2
            sess["username"] = "notowner"
        assert client.get("/api/agents/agt_000000000000").status_code == 403


# ---------------------------------------------------------------------------
# Review hardening: defects found during PR review, with regression tests
# ---------------------------------------------------------------------------

class TestReviewHardening:
    def test_verify_malformed_agent_id_fails_closed_not_raises(self):
        """A non-string agent_id is denied, never a crash that could bypass a gate."""
        reg = _registry()
        for bad in ({"x": 1}, ["a"], 123, object()):
            result = reg.verify(bad)
            assert result.ok is False

    def test_get_malformed_agent_id_returns_none(self):
        reg = _registry()
        assert reg.get({"x": 1}) is None
        assert reg.get(["a"]) is None

    def test_boundary_check_malformed_agent_id_is_denied(self):
        reg = _registry()
        guard = BoundaryGuard(identities=reg, policy=_owner())
        assert guard.check_tool({"x": 1}, "calculator", user_id=1).allowed is False

    def test_one_tool_call_counts_once(self):
        """A request+result pair is one outcome, not two successes."""
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        one_call = [
            {"event": "tool_request", "allowed": True, "agent_id": a.agent_id},
            {"event": "tool_result", "allowed": True, "agent_id": a.agent_id},
        ]
        report = TrustEvaluator(audit=reg.audit).evaluate(a, history=one_call)
        assert report.evidence["successes"] == 1

    def test_denied_request_counts_as_denial_not_failure(self):
        reg = _registry()
        a = reg.register(name="w", role="worker", owner_id=1, owner_approved=True)
        history = [{"event": "tool_request", "allowed": False, "agent_id": a.agent_id}] * 3
        report = TrustEvaluator(audit=reg.audit).evaluate(a, history=history)
        assert report.evidence["denials"] == 3
        assert report.evidence["failures"] == 0

    def test_cannot_reactivate_child_while_parent_suspended(self):
        reg = _registry()
        parent = reg.register(name="p", role="orchestrator", owner_id=1,
                              tools=["calculator"], owner_approved=True)
        child = reg.register(name="c", role="worker", owner_id=1, parent_id=parent.agent_id,
                             tools=["calculator"], owner_approved=True)
        reg.suspend(parent.agent_id, owner_approved=True)  # cascades
        with pytest.raises(IdentityError):
            reg.reactivate(child.agent_id, owner_approved=True)
        # Reactivating the parent first, then the child, works.
        reg.reactivate(parent.agent_id, owner_approved=True)
        reg.reactivate(child.agent_id, owner_approved=True)
        assert reg.verify(child.agent_id).ok is True


# ---------------------------------------------------------------------------
# Backward compatibility: identity is optional and additive
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_audit_entry_without_agent_id_is_unchanged(self):
        audit = AuditLog(":memory:")
        entry = audit.record("tool_request", 1, "calculator", True, "safe tool")
        assert "agent_id" not in entry
        assert entry["event"] == "tool_request"

    def test_audit_entry_with_agent_id_adds_only_that_key(self):
        audit = AuditLog(":memory:")
        entry = audit.record("tool_request", 1, "calculator", True, "safe", agent_id="agt_x")
        assert entry["agent_id"] == "agt_x"

    def test_loop_run_without_agent_id_is_unchanged(self, tmp_path):
        from genesis_protocol.agentic.agent_loop import AgentLoop
        from genesis_protocol.agentic.memory import AgentMemory
        from genesis_protocol.agentic.tasks import TaskStore

        loop = AgentLoop(
            memory=AgentMemory(":memory:"),
            tasks=TaskStore(str(tmp_path / "t.json")),
            policy=_owner(),
            audit=AuditLog(":memory:"),
        )
        result = loop.run(
            user_id=1, goal="calc",
            steps=[{"type": "tool", "tool": "calculator", "params": {"expression": "2+2"}}],
        )
        assert result["state"] == "completed"
        assert result["agent_id"] is None

    def test_existing_policy_decision_shape_unchanged(self):
        decision = AgentPolicy(owner_ids=[1]).authorize_tool(1, "calculator", permission="safe")
        assert decision.to_dict() == {
            "allowed": True, "reason": "safe tool", "requires_owner_approval": False
        }
