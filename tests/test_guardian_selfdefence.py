"""AI Guardian & self-defence (V7 P5).

Covers the P5 contract:

* threat intelligence: trusted sources, relevance to Genesis dependencies,
  provenance (links, timestamps) and confidence
* runtime threat detection: auth, webhook, API, identity spoofing, privilege
  escalation, secret exposure, unexpected tool execution
* agent behaviour monitoring: tool patterns, policy violations, repeated denials,
  identity/history correlation
* system health: resources, memory/database integrity, behaviour change
* defensive response: read-only, reversible, owner-gated; no automatic deletion,
  credential rotation, code modification or deployment
* forensics: tamper-evident records, timelines, no attribution without evidence
* adversarial verification: simulated attacks, spoofing, malicious tool requests,
  secret leakage, false alerts, with detection accuracy and false-positive counts
* backward compatibility: no change to existing routes, policy or loop

Hermetic: the process-wide audit log, security log, identity registry, credential
store, memory and task stores are pointed at in-memory instances, so nothing is
written to ``data/`` and no real permission is consulted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import genesis_protocol.agentic.audit as audit_mod  # noqa: E402
import genesis_protocol.agentic.credentials as cred_mod  # noqa: E402
import genesis_protocol.agentic.identity_registry as idreg_mod  # noqa: E402
import genesis_protocol.agentic.policy as policy_mod  # noqa: E402
import genesis_protocol.guardian.events as events_mod  # noqa: E402
from genesis_protocol.agentic.audit import AuditLog  # noqa: E402
from genesis_protocol.agentic.credentials import CredentialStore  # noqa: E402
from genesis_protocol.agentic.identity_registry import IdentityRegistry  # noqa: E402
from genesis_protocol.agentic.policy import AgentPolicy  # noqa: E402
from genesis_protocol.guardian import (  # noqa: E402
    FORBIDDEN_ACTIONS,
    Guardian,
    HealthMonitor,
    RuntimeDetector,
    SecurityEventLog,
    ThreatIntel,
)
from genesis_protocol.guardian.behaviour import BehaviourMonitor  # noqa: E402
from genesis_protocol.guardian.response import DefensiveResponder  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """In-memory audit/security/identity/credential/policy singletons."""
    audit = AuditLog(":memory:")
    monkeypatch.setattr(audit_mod, "_default", audit, raising=False)
    monkeypatch.setattr(audit_mod, "get_audit_log", lambda *a, **k: audit)

    security = SecurityEventLog(":memory:")
    monkeypatch.setattr(events_mod, "_default", security, raising=False)
    monkeypatch.setattr(events_mod, "get_security_log", lambda *a, **k: security)

    creds = CredentialStore(":memory:")
    monkeypatch.setattr(cred_mod, "_default", creds, raising=False)
    monkeypatch.setattr(cred_mod, "get_credential_store", lambda *a, **k: creds)

    identities = IdentityRegistry(path=":memory:", credentials=creds, audit=audit)
    monkeypatch.setattr(idreg_mod, "_default", identities, raising=False)
    monkeypatch.setattr(idreg_mod, "get_identity_registry", lambda *a, **k: identities)

    monkeypatch.setattr(policy_mod, "_default", AgentPolicy(owner_ids={1}), raising=False)
    monkeypatch.setattr(policy_mod, "get_agent_policy", lambda: AgentPolicy(owner_ids={1}), raising=False)

    # Keep health checks off the real data/ files.
    monkeypatch.setenv("GLUTEN_MEMORY_DB", ":memory:")
    monkeypatch.setenv("GLUTEN_TASK_DB", str(REPO_ROOT / "data" / "__nonexistent_task_store__.json"))

    return {"audit": audit, "security": security, "identities": identities, "creds": creds}


def _guardian(env, observations=None):
    return Guardian(
        security_log=env["security"],
        detector=RuntimeDetector(audit=env["audit"], security_log=env["security"],
                                 identity_registry=env["identities"]),
        behaviour=BehaviourMonitor(audit=env["audit"], identity_registry=env["identities"]),
    )


# ---------------------------------------------------------------------------
# 1. Threat intelligence
# ---------------------------------------------------------------------------

class TestThreatIntelligence:
    def test_trusted_sources_present(self):
        from genesis_protocol.guardian import TRUSTED_SOURCES
        for key in ("cert-in", "cisa", "nvd", "owasp"):
            assert key in TRUSTED_SOURCES

    def test_advisory_keeps_source_link_and_timestamp(self):
        ti = ThreatIntel(dependencies={"httpx"})
        a = ti.parse({"id": "CVE-2024-1111", "title": "httpx flaw", "url": "https://nvd.nist.gov/x",
                      "published": "2024-05-01", "affected": ["httpx"]}, "nvd")
        assert a.url == "https://nvd.nist.gov/x"
        assert a.published == "2024-05-01"
        assert a.retrieved_at

    def test_confidence_is_explained(self):
        ti = ThreatIntel(dependencies={"httpx"})
        a = ti.parse({"id": "CVE-2024-1111", "title": "httpx flaw", "url": "https://nvd.nist.gov/x",
                      "affected": ["httpx"]}, "nvd")
        assert 0.0 < a.confidence <= 1.0
        assert a.confidence_reason

    def test_relevant_to_genesis_dependencies(self):
        ti = ThreatIntel(dependencies={"httpx", "flask-limiter"})
        advisories = ti.parse_many([
            {"id": "CVE-1", "title": "httpx issue", "url": "u", "affected": ["httpx"]},
            {"id": "CVE-2", "title": "unrelated", "url": "u", "affected": ["someotherlib"]},
        ], "nvd")
        relevant = ti.relevant_only(advisories)
        assert [a.advisory_id for a in relevant] == ["CVE-1"]

    def test_no_fabricated_intelligence(self):
        ti = ThreatIntel(dependencies={"httpx"})
        assert ti.parse_many([], "nvd") == []

    def test_missing_link_reduces_confidence(self):
        ti = ThreatIntel(dependencies={"httpx"})
        a = ti.parse({"id": "CVE-1", "title": "httpx", "url": "", "affected": ["httpx"]}, "vendor")
        assert "no source link" in a.confidence_reason

    def test_dependencies_read_from_requirements(self):
        from genesis_protocol.guardian.threat_intel import genesis_dependencies
        deps = genesis_dependencies(REPO_ROOT)
        assert "httpx" in deps  # a real Genesis dependency


# ---------------------------------------------------------------------------
# 2. Runtime threat detection
# ---------------------------------------------------------------------------

class TestRuntimeDetection:
    def test_suspicious_auth_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "auth", "event": "login_failed", "actor": "attacker"}] * 6
        findings = detector.detect_auth(obs)
        assert any(f.detector == "auth_bruteforce" for f in findings)

    def test_single_auth_failure_is_not_a_finding(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        assert detector.detect_auth([{"category": "auth", "event": "login_failed", "actor": "u"}]) == []

    def test_webhook_abuse_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "webhook", "event": "rejected", "actor": "1.2.3.4"}] * 5
        assert any(f.detector == "webhook_abuse" for f in detector.detect_webhook_abuse(obs))

    def test_unusual_api_activity_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "api", "event": "call", "actor": "svc"}] * 61
        assert any(f.detector == "api_burst" for f in detector.detect_api_burst(obs))

    def test_identity_spoofing_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_result", 1, "calculator", True, "ok", agent_id="ghost-agent")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        findings = detector.detect_identity_spoofing(audit.tail())
        assert any(f.detector == "identity_spoofing" for f in findings)

    def test_privilege_escalation_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "deploy", False, "privileged operation requires owner",
                     agent_id="ghost-agent")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        findings = detector.detect_privilege_escalation(audit.tail())
        assert any(f.detector == "privilege_escalation" for f in findings)

    def test_secret_exposure_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "api", "event": "call", "actor": "svc",
                "evidence": {"note": "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}}]
        findings = detector.detect_secret_exposure(obs)
        assert any(f.detector == "secret_exposure" for f in findings)
        # The value itself is never stored, only the kind.
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in json.dumps(findings[0].to_dict())

    def test_unexpected_tool_execution_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "definitely_not_a_tool", True, "allowed", agent_id="a")
        audit.record("tool_result", 1, "definitely_not_a_tool", True, "ok", agent_id="a")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        findings = detector.detect_unexpected_tool_execution(audit.tail())
        assert any(f.detector == "unregistered_tool" for f in findings)

    def test_execution_after_denial_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "web_search", False, "denied", agent_id="a")
        audit.record("tool_result", 1, "web_search", True, "ok", agent_id="a")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        findings = detector.detect_unexpected_tool_execution(audit.tail())
        assert any(f.detector == "execution_after_denial" for f in findings)

    def test_denial_of_one_tool_does_not_flag_another(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "deploy", False, "denied", agent_id="a")
        audit.record("tool_result", 1, "calculator", True, "ok", agent_id="a")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        findings = detector.detect_unexpected_tool_execution(audit.tail())
        assert not any(f.detector == "execution_after_denial" for f in findings)


# ---------------------------------------------------------------------------
# 3. Agent behaviour monitoring
# ---------------------------------------------------------------------------

class TestBehaviourMonitoring:
    def _monitor(self, _isolate):
        return BehaviourMonitor(audit=_isolate["audit"], identity_registry=_isolate["identities"])

    def test_unusual_tool_variety(self, _isolate):
        audit = _isolate["audit"]
        for tool in [f"t{i}" for i in range(9)]:
            audit.record("tool_result", 1, tool, True, "ok", agent_id="busy")
        findings = self._monitor(_isolate).detect_unusual_tool_patterns("busy", audit.tail())
        assert any(f.detector == "unusual_tool_variety" for f in findings)

    def test_policy_violation(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "web_search", False, "denied", agent_id="a")
        findings = self._monitor(_isolate).detect_policy_violations("a", audit.tail())
        assert any(f.detector == "policy_violation" for f in findings)

    def test_repeated_denials(self, _isolate):
        audit = _isolate["audit"]
        for _ in range(3):
            audit.record("tool_request", 1, "web_search", False, "denied", agent_id="a")
        findings = self._monitor(_isolate).detect_repeated_denials("a", audit.tail())
        assert any(f.detector == "repeated_denied_actions" for f in findings)

    def test_grant_escape(self, _isolate):
        identities = _isolate["identities"]
        identities.register(name="reader", role="analyst", owner_id=1, tools=["calculator"],
                            owner_approved=True, agent_id="agt_aaaaaaaaaaaa")
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "code_execution", True, "allowed", agent_id="agt_aaaaaaaaaaaa")
        findings = self._monitor(_isolate).detect_grant_escape("agt_aaaaaaaaaaaa", audit.tail())
        assert any(f.detector == "grant_escape" for f in findings)

    def test_correlate_identity_and_history(self, _isolate):
        identities = _isolate["identities"]
        identities.register(name="worker", role="operator", owner_id=1, tools=["calculator"],
                            owner_approved=True, agent_id="agt_bbbbbbbbbbbb")
        audit = _isolate["audit"]
        audit.record("tool_result", 1, "calculator", True, "ok", agent_id="agt_bbbbbbbbbbbb")
        view = self._monitor(_isolate).correlate("agt_bbbbbbbbbbbb")
        assert view["identity"]["agent_id"] == "agt_bbbbbbbbbbbb"
        assert view["verification"]["ok"] is True
        assert view["history_size"] >= 1
        assert view["timeline"]


# ---------------------------------------------------------------------------
# 4. System health
# ---------------------------------------------------------------------------

class TestSystemHealth:
    def test_memory_db_integrity_ok(self, tmp_path):
        import sqlite3
        db = tmp_path / "mem.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE memories (id TEXT)")
        conn.commit()
        conn.close()
        findings = HealthMonitor(memory_db=str(db)).check_memory_db()
        assert any(f.detector == "memory_db_ok" for f in findings)

    def test_corrupt_memory_db_detected(self, tmp_path):
        db = tmp_path / "mem.db"
        db.write_bytes(b"this is not a sqlite database at all, not even close" * 10)
        findings = HealthMonitor(memory_db=str(db)).check_memory_db()
        assert any(f.detector in ("memory_db_corrupt", "memory_db_unreadable") for f in findings)

    def test_missing_memory_db_reported(self, tmp_path):
        findings = HealthMonitor(memory_db=str(tmp_path / "nope.db")).check_memory_db()
        assert any(f.detector == "memory_db_missing" for f in findings)

    def test_resource_check_returns_findings(self):
        findings = HealthMonitor().check_resources()
        # Never raises; may be empty on a healthy host.
        assert isinstance(findings, list)

    def test_behaviour_change_detected(self):
        findings = HealthMonitor.detect_behaviour_change(
            {"error_rate": 0.01}, {"error_rate": 0.5}, tolerance=0.1)
        assert any(f.detector == "behaviour_change" for f in findings)

    def test_no_change_no_finding(self):
        assert HealthMonitor.detect_behaviour_change({"x": 1}, {"x": 1}, tolerance=0.0) == []


# ---------------------------------------------------------------------------
# 5. Defensive response (read-only, reversible, owner-gated)
# ---------------------------------------------------------------------------

class TestDefensiveResponse:
    def test_recommendations_are_reversible_and_non_automatic(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "deploy", False, "denied", agent_id="ghost")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        recs = DefensiveResponder().recommend_many(detector.detect_privilege_escalation(audit.tail()))
        assert recs
        assert all(r.reversible and not r.automatic for r in recs)

    def test_privileged_actions_require_owner_approval(self):
        rec = DefensiveResponder().recommend(
            {"detector": "identity_spoofing", "severity": "high", "subject": "ghost"})
        assert rec.action == "suspend_identity"
        assert rec.requires_owner_approval is True
        assert rec.automatic is False

    def test_forbidden_actions_are_refused(self):
        responder = DefensiveResponder()
        for action in FORBIDDEN_ACTIONS:
            responder._CATALOG["probe"] = (action, "actor", "x", True, "x")
            with pytest.raises(ValueError):
                responder.recommend({"detector": "probe", "severity": "high"})
            del responder._CATALOG["probe"]

    def test_info_findings_produce_no_recommendation(self):
        assert DefensiveResponder().recommend(
            {"detector": "memory_db_ok", "severity": "info"}) is None

    def test_no_credential_rotation_is_automatic(self):
        rec = DefensiveResponder().recommend(
            {"detector": "secret_exposure", "severity": "critical", "actor": "svc"})
        assert rec.action == "rotate_secret"
        assert rec.requires_owner_approval and not rec.automatic

    def test_guardian_takes_no_action(self, _isolate):
        report = _guardian(_isolate).monitor()
        assert report.read_only is True
        assert report.actions_taken == []


# ---------------------------------------------------------------------------
# 6. Forensics
# ---------------------------------------------------------------------------

class TestForensics:
    def test_chain_is_intact_after_appends(self):
        log = SecurityEventLog(":memory:")
        for i in range(5):
            log.record("auth", f"event{i}", severity="low")
        assert log.verify() == {"ok": True, "broken_at": -1, "total": 5}

    def test_tampering_is_detected(self):
        log = SecurityEventLog(":memory:")
        for i in range(5):
            log.record("auth", f"event{i}")
        log._memory[2]["severity"] = "critical"  # edit a stored entry
        result = log.verify()
        assert result["ok"] is False and result["broken_at"] == 2

    def test_deletion_is_detected(self):
        log = SecurityEventLog(":memory:")
        for i in range(5):
            log.record("auth", f"event{i}")
        del log._memory[1]
        assert log.verify()["ok"] is False

    def test_events_have_timestamps_and_sequence(self):
        log = SecurityEventLog(":memory:")
        log.record("tool", "x")
        log.record("tool", "y")
        rows = log.entries()
        assert [r["seq"] for r in rows] == [0, 1]
        assert all(r["ts"] for r in rows)

    def test_secrets_are_redacted_in_the_log(self):
        log = SecurityEventLog(":memory:")
        log.record("secret", "observed", evidence={"detail": "token=ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
        assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in json.dumps(log.entries())

    def test_incident_timeline_is_ordered(self):
        log = SecurityEventLog(":memory:")
        log.record("auth", "one", actor="a")
        log.record("tool", "two", actor="a")
        log.record("auth", "three", actor="b")
        timeline = log.incident_timeline(actor="a")
        assert [e["event"] for e in timeline] == ["one", "two"]
        assert timeline == sorted(timeline, key=lambda r: r["ts"])

    def test_unknown_category_is_refused(self):
        with pytest.raises(ValueError):
            SecurityEventLog(":memory:").record("not_a_category", "x")

    def test_guardian_asserts_no_attribution(self, _isolate):
        timeline = _guardian(_isolate).incident_timeline(actor="ghost")
        assert "attribution" in timeline["note"].lower()
        assert timeline["chain"]["ok"] is True


# ---------------------------------------------------------------------------
# 7. Adversarial verification + false-positive analysis
# ---------------------------------------------------------------------------

class TestAdversarialVerification:
    def test_simulated_bruteforce_attack_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "auth", "event": "login_failed", "actor": "botnet"}] * 10
        findings = detector.scan_observations(obs)
        assert any(f.detector == "auth_bruteforce" and f.severity == "high" for f in findings)

    def test_spoofed_identity_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_result", 1, "calculator", True, "ok", agent_id="forged")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        assert any(f.detector == "identity_spoofing" for f in detector.scan_audit())

    def test_malicious_tool_request_detected(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "deploy", False, "privileged operation requires owner",
                     agent_id="ghost")
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        assert any(f.detector == "privilege_escalation" for f in detector.scan_audit())

    def test_secret_leakage_detected(self, _isolate):
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        obs = [{"category": "api", "event": "call", "actor": "svc",
                "evidence": {"k": "AKIAABCDEFGHIJKLMNOP"}}]
        assert any(f.detector == "secret_exposure" for f in detector.scan_observations(obs))

    def test_detection_accuracy_on_labelled_attacks(self, _isolate):
        """Every labelled attack is detected (recall on the known set)."""
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        attacks = [
            ({"category": "auth", "event": "login_failed", "actor": "a"}, "auth_bruteforce"),
            ({"category": "webhook", "event": "invalid_secret", "actor": "b"}, "webhook_abuse"),
            ({"category": "api", "event": "call", "actor": "c",
              "evidence": {"k": "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"}}, "secret_exposure"),
        ]
        # Repeat the thresholded ones enough to cross the bar.
        obs = []
        for event, _ in attacks:
            obs += [event] * 6
        detected = {f.detector for f in detector.scan_observations(obs)}
        for _, expected in attacks:
            assert expected in detected, f"missed {expected}"

    def test_false_positive_rate_on_benign_traffic(self, _isolate):
        """Benign traffic below every threshold must produce no findings."""
        detector = RuntimeDetector(audit=_isolate["audit"], security_log=_isolate["security"])
        benign = [
            {"category": "auth", "event": "login_success", "actor": "user"},
            {"category": "api", "event": "call", "actor": "user"},
            {"category": "webhook", "event": "accepted", "actor": "telegram"},
            {"category": "api", "event": "call", "actor": "user", "evidence": {"note": "ok"}},
        ]
        findings = detector.scan_observations(benign)
        assert findings == []

    def test_benign_audit_has_no_findings(self, _isolate):
        audit = _isolate["audit"]
        audit.record("tool_request", 1, "calculator", True, "allowed", agent_id=None)
        audit.record("tool_result", 1, "calculator", True, "ok", agent_id=None)
        detector = RuntimeDetector(audit=audit, security_log=_isolate["security"],
                                   identity_registry=_isolate["identities"])
        # No agent id -> nothing to spoof; no denial -> no escalation.
        assert [f.detector for f in detector.scan_audit()] == []

    def test_full_pass_false_positive_budget(self, _isolate):
        """A healthy system yields only informational findings, no false alerts."""
        report = _guardian(_isolate).monitor()
        high = [f for f in report.findings if f["severity"] in ("high", "critical")]
        assert high == [], f"unexpected high-severity findings on a clean system: {high}"


# ---------------------------------------------------------------------------
# 8. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_audit_log_unchanged(self, _isolate):
        entry = _isolate["audit"].record("tool_request", 1, "calculator", True, "allowed")
        assert set(entry) >= {"ts", "event", "user_id", "tool", "allowed", "reason"}

    def test_guardian_status_is_read_only(self, _isolate):
        status = _guardian(_isolate).status()
        assert status["read_only"] is True
        assert status["autonomous_actions"] == []

    def test_report_serialisable(self, _isolate):
        report = _guardian(_isolate).monitor()
        json.dumps(report.to_dict())

    def test_guardian_web_routes_owner_gated(self):
        import web.app as appmod
        appmod.app.config["TESTING"] = True
        client = appmod.app.test_client()
        assert client.get("/api/guardian/status").status_code == 401
        assert client.post("/api/guardian/scan", json={}).status_code == 401
        assert client.get("/api/guardian/forensics").status_code == 401

    def test_guardian_scan_is_read_only(self, _isolate):
        import web.app as appmod
        appmod.app.config["TESTING"] = True
        client = appmod.app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "owner"
        resp = client.post("/api/guardian/scan", json={"observations": []})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["read_only"] is True
        assert body["actions_taken"] == []
