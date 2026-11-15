"""Controlled autonomous defence (V7 P6).

Covers the P6 contract:

* severity classification with evidence-based, explained confidence
* correlation of security events across agents, tools, identities and sessions
* automatic alerts for confirmed incidents
* policy-controlled, reversible low-risk defensive actions
* owner approval for medium/high-risk operations
* an explicit allow-list of permitted defensive actions
* rollback and recovery for every reversible action
* an emergency kill switch
* rate limits and action budgets
* protection against false positives and repeated automated responses
* hard prohibitions: no automatic account/data deletion, credential rotation
  without approval, trust-root/policy/threshold change, self-authority change,
  deployment or approval-gate bypass

Hermetic: in-memory security log, kill switch, ledger, budget and alert sink.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from genesis_protocol.guardian import (  # noqa: E402
    ALLOWED_ACTIONS,
    NEVER_ACTIONS,
    ActionBudget,
    ActionCatalog,
    AdminAlertBridge,
    ClassifiedFinding,
    Correlator,
    DefenceEngine,
    KillSwitch,
    LocalActionSink,
    SecurityEventLog,
    SeverityClassifier,
)
from genesis_protocol.guardian.actions import ActionNotAllowed  # noqa: E402
from genesis_protocol.guardian.severity import SEVERITY_RANK  # noqa: E402


def _finding(detector, severity="medium", **kw):
    data = {"detector": detector, "severity": severity}
    data.update(kw)
    return data


def _engine(per_target=1, cooldown=100, sink=None, alerts=None, budget=None):
    log = SecurityEventLog(":memory:")
    sink = sink if sink is not None else LocalActionSink(":memory:", cooldown_seconds=cooldown)
    engine = DefenceEngine(
        security_log=log,
        kill_switch=KillSwitch(":memory:"),
        action_sink=sink,
        budget=budget or ActionBudget(per_target=per_target, cooldown_seconds=cooldown),
        alert_sink=alerts,
    )
    return engine, log, sink


# ---------------------------------------------------------------------------
# 1. Severity + confidence
# ---------------------------------------------------------------------------

class TestSeverityClassification:
    def test_known_detector_gets_baseline_severity(self):
        c = SeverityClassifier().classify(_finding("secret_exposure", "critical"))
        assert c.severity == "critical"
        assert 0.0 <= c.confidence <= 1.0
        assert c.confidence_reasons

    def test_unknown_detector_lowers_confidence(self):
        c = SeverityClassifier().classify(_finding("mystery_detector", "high"))
        assert any("not in the catalogue" in r for r in c.confidence_reasons)
        assert c.confidence < 0.5

    def test_threshold_evidence_raises_confidence(self):
        weak = SeverityClassifier().classify(
            _finding("auth_bruteforce", "medium", evidence={"count": 5, "threshold": 5}))
        strong = SeverityClassifier().classify(
            _finding("auth_bruteforce", "medium", evidence={"count": 20, "threshold": 5}))
        assert strong.confidence > weak.confidence
        assert any("threshold" in r for r in strong.confidence_reasons)

    def test_identity_verification_lowers_confidence(self):
        spoof = SeverityClassifier().classify(_finding("identity_spoofing", "high", verified=False))
        good = SeverityClassifier().classify(_finding("identity_spoofing", "high", verified=True))
        assert spoof.confidence > good.confidence

    def test_corroboration_raises_confidence(self):
        findings = [
            _finding("auth_bruteforce", "medium", actor="a", evidence={"count": 12, "threshold": 5}),
            _finding("api_burst", "low", actor="a"),
            _finding("repeated_denials", "medium", actor="a"),
        ]
        classified = SeverityClassifier().classify_many(findings)
        assert any("corroborated" in r for r in classified[0].confidence_reasons)

    def test_secret_pattern_kind_raises_confidence(self):
        c = SeverityClassifier().classify(
            _finding("secret_exposure", "critical", evidence={"kinds": ["github_token"]}))
        assert any("secret pattern" in r for r in c.confidence_reasons)

    def test_is_confirmed_requires_confidence_and_severity(self):
        low = ClassifiedFinding(detector="x", severity="low", confidence=0.9)
        assert SeverityClassifier.is_confirmed(low) is True
        info = ClassifiedFinding(detector="x", severity="info", confidence=0.9)
        assert SeverityClassifier.is_confirmed(info) is False
        unsure = ClassifiedFinding(detector="x", severity="high", confidence=0.5)
        assert SeverityClassifier.is_confirmed(unsure) is False


# ---------------------------------------------------------------------------
# 2. Correlation
# ---------------------------------------------------------------------------

class TestCorrelation:
    def test_findings_sharing_an_actor_cluster(self):
        c = SeverityClassifier().classify_many([
            _finding("auth_bruteforce", "medium", actor="attacker", evidence={"count": 12, "threshold": 5}),
            _finding("api_burst", "medium", actor="attacker"),
        ])
        incidents = Correlator().correlate(c)
        assert len(incidents) == 1
        assert set(incidents[0].detectors) == {"auth_bruteforce", "api_burst"}

    def test_different_actors_stay_separate(self):
        c = SeverityClassifier().classify_many([
            _finding("auth_bruteforce", "medium", actor="a", evidence={"count": 12, "threshold": 5}),
            _finding("auth_bruteforce", "medium", actor="b", evidence={"count": 12, "threshold": 5}),
        ])
        incidents = Correlator().correlate(c)
        assert len(incidents) == 2

    def test_correlation_raises_incident_confidence(self):
        c = SeverityClassifier().classify_many([
            _finding("identity_spoofing", "high", agent_id="ghost", verified=False),
            _finding("grant_escape", "high", agent_id="ghost"),
        ])
        incidents = Correlator().correlate(c)
        top = max(f["confidence"] for f in incidents[0].findings)
        assert incidents[0].confidence >= top

    def test_session_attribution_from_audit(self):
        findings = [{"detector": "api_burst", "actor": "a"}]
        Correlator.attribute_sessions(findings, [{"agent_id": "a", "session": "S-1"}])
        assert findings[0]["session"] == "S-1"

    def test_incidents_serialisable(self):
        c = SeverityClassifier().classify_many([_finding("auth_bruteforce", "medium", actor="a")])
        json.dumps([i.to_dict() for i in Correlator().correlate(c)])


# ---------------------------------------------------------------------------
# 3. Allow-list and prohibited actions
# ---------------------------------------------------------------------------

class TestActionAllowList:
    def test_allow_list_is_small_and_reversible(self):
        for spec in ALLOWED_ACTIONS.values():
            assert spec.reversible is True
            assert spec.rollback

    def test_only_low_risk_may_be_automatic(self):
        for spec in ALLOWED_ACTIONS.values():
            if spec.automatic_allowed:
                assert spec.risk == "low"

    def test_forbidden_actions_are_not_on_the_allow_list(self):
        assert not (NEVER_ACTIONS & set(ALLOWED_ACTIONS))

    def test_catalog_refuses_forbidden_action(self):
        catalog = ActionCatalog()
        for action in NEVER_ACTIONS:
            assert catalog.allowed(action) is False
            with pytest.raises(ActionNotAllowed):
                catalog.require(action)

    def test_catalog_refuses_unknown_action(self):
        with pytest.raises(ActionNotAllowed):
            ActionCatalog().require("teleport_the_database")


# ---------------------------------------------------------------------------
# 4. Kill switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_default_is_disengaged(self):
        assert KillSwitch(":memory:").is_engaged() is False

    def test_engage_and_disengage(self):
        ks = KillSwitch(":memory:")
        ks.engage("drill")
        assert ks.is_engaged() is True
        assert ks.status()["reason"] == "drill"
        ks.disengage(owner_approved=True, actor="owner")
        assert ks.is_engaged() is False

    def test_disengage_requires_owner(self):
        ks = KillSwitch(":memory:")
        ks.engage()
        with pytest.raises(PermissionError):
            ks.disengage(owner_approved=False)

    def test_unreadable_state_fails_closed(self, tmp_path):
        bad = tmp_path / "ks.json"
        bad.write_text("{not json")
        assert KillSwitch(str(bad)).is_engaged() is True

    def test_kill_switch_stops_automatic_actions(self):
        engine, _, sink = _engine()
        engine.kill_switch.engage("stop")
        rep = engine.defend([_finding("auth_bruteforce", "medium", actor="a",
                                      evidence={"count": 12, "threshold": 5})])
        assert rep.actions_performed == []
        assert sink.is_throttled("a") is False
        assert any("kill switch" in d["reason"] for d in rep.decisions)


# ---------------------------------------------------------------------------
# 5. Budget / rate limits
# ---------------------------------------------------------------------------

class TestActionBudget:
    def test_per_target_cooldown(self):
        b = ActionBudget(per_target=1, cooldown_seconds=1000)
        assert b.check("k").allowed is True
        b.consume("k")
        d = b.check("k")
        assert d.allowed is False and d.retry_after_seconds > 0

    def test_global_cap(self):
        b = ActionBudget(per_target=1, cooldown_seconds=0, global_cap=2, global_window_seconds=1000)
        for k in ("a", "b"):
            assert b.check(k).allowed
            b.consume(k)
        assert b.check("c").allowed is False

    def test_consecutive_cap(self):
        b = ActionBudget(per_target=1, cooldown_seconds=0, global_cap=100, max_consecutive=2)
        for k in ("a", "b"):
            b.consume(k)
        assert b.check("c").allowed is False
        b.note_quiet_pass()
        assert b.check("c").allowed is True

    def test_repeated_signal_does_not_repeat_action(self):
        engine, _, sink = _engine(per_target=1, cooldown=1000)
        finding = _finding("auth_bruteforce", "medium", actor="a", evidence={"count": 12, "threshold": 5})
        first = engine.defend([finding])
        second = engine.defend([finding])
        assert len(first.actions_performed) == 1
        assert second.actions_performed == []
        assert any("cooldown" in d["reason"] for d in second.decisions)


# ---------------------------------------------------------------------------
# 6. Reversible actions + rollback
# ---------------------------------------------------------------------------

class TestReversibleActions:
    def test_low_risk_action_is_performed_and_reversible(self):
        engine, _, sink = _engine()
        rep = engine.defend([_finding("auth_bruteforce", "medium", actor="attacker",
                                      evidence={"count": 12, "threshold": 5})])
        assert len(rep.actions_performed) == 1
        assert sink.is_throttled("attacker") is True
        assert engine.rollback("rate_limit_actor", "attacker") is True
        assert sink.is_throttled("attacker") is False

    def test_rollback_token_returned(self):
        engine, _, _ = _engine()
        rep = engine.defend([_finding("webhook_abuse", "medium", actor="1.2.3.4",
                                      evidence={"count": 12, "threshold": 5})])
        assert rep.actions_performed[0]["rollback_token"]

    def test_rollback_of_non_permitted_action_refused(self):
        engine, _, _ = _engine()
        with pytest.raises(ActionNotAllowed):
            engine.rollback("delete_account", "x")

    def test_ledger_corruption_does_not_crash(self, tmp_path):
        bad = tmp_path / "ledger.json"
        bad.write_text("not json at all")
        sink = LocalActionSink(str(bad))
        assert sink.is_throttled("x") is False
        assert sink.status()["active_cooldowns"] == 0


# ---------------------------------------------------------------------------
# 7. Owner approval for medium/high risk
# ---------------------------------------------------------------------------

class TestOwnerApproval:
    def test_identity_spoofing_is_proposed_not_performed(self):
        engine, _, sink = _engine()
        rep = engine.defend([_finding("identity_spoofing", "high", agent_id="ghost", verified=False)])
        assert rep.actions_performed == []
        assert any(p["action"] == "suspend_identity" for p in rep.proposals)
        assert sink.is_throttled("ghost") is False

    def test_secret_exposure_needs_corroboration(self):
        engine, _, _ = _engine()
        rep = engine.defend([_finding("secret_exposure", "critical", actor="svc",
                                      evidence={"kinds": ["github_token"]})])
        assert rep.actions_performed == []
        assert any(p["action"] == "rotate_secret" for p in rep.proposals)
        assert any("corroboration" in p["reason"] for p in rep.proposals)

    def test_corroborated_secret_exposure_still_not_automatic(self):
        engine, _, sink = _engine()
        rep = engine.defend([
            _finding("secret_exposure", "critical", actor="svc", evidence={"kinds": ["github_token"]}),
            _finding("identity_spoofing", "high", actor="svc", verified=False),
        ])
        # rotate_secret is high risk -> never automatic, only proposed.
        assert rep.actions_performed == []
        assert any(p["action"] == "rotate_secret" for p in rep.proposals)

    def test_high_impact_requires_high_severity_floor(self):
        engine, _, _ = _engine()
        # identity_spoofing at only 'low' severity must not propose a suspension.
        rep = engine.defend([_finding("identity_spoofing", "low", agent_id="ghost")])
        assert all(p["action"] != "suspend_identity" for p in rep.proposals)


# ---------------------------------------------------------------------------
# 8. Automatic alerts
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_confirmed_high_incident_raises_alert(self):
        seen = []
        engine, _, _ = _engine(alerts=lambda inc: seen.append(inc))
        engine.defend([_finding("identity_spoofing", "high", agent_id="ghost", verified=False)])
        assert len(seen) == 1

    def test_low_severity_does_not_alert(self):
        seen = []
        engine, _, _ = _engine(alerts=lambda inc: seen.append(inc))
        engine.defend([_finding("api_burst", "low", actor="a")])
        assert seen == []

    def test_alert_failure_does_not_break_pass(self):
        def boom(inc):
            raise RuntimeError("telegram down")

        engine, _, _ = _engine(alerts=boom)
        rep = engine.defend([_finding("identity_spoofing", "high", agent_id="ghost", verified=False)])
        assert any(a.get("delivered") is False for a in rep.alerts)

    def test_admin_alert_bridge_uses_canonical_manager(self):
        class FakeManager:
            def __init__(self):
                self.calls = []

            def send_alert(self, *a, **k):
                self.calls.append((a, k))

        mgr = FakeManager()
        result = AdminAlertBridge(mgr)({"incident_id": "INC-1", "severity": "high",
                                        "confidence": 0.9, "detectors": ["x"], "entities": {}})
        assert result["delivered"] is True and mgr.calls


# ---------------------------------------------------------------------------
# 9. False positives / repeat protection
# ---------------------------------------------------------------------------

class TestFalsePositiveProtection:
    def test_benign_findings_produce_no_action(self):
        engine, _, _ = _engine()
        rep = engine.defend([_finding("memory_db_ok", "info")])
        assert rep.actions_performed == [] and rep.proposals == []

    def test_low_confidence_finding_not_confirmed(self):
        engine, _, _ = _engine()
        # api_burst at low severity, no threshold evidence -> not confirmed.
        rep = engine.defend([_finding("api_burst", "low", actor="a")])
        assert rep.incidents == []

    def test_repeated_passes_do_not_loop_actions(self):
        engine, _, _ = _engine(per_target=1, cooldown=1000)
        finding = _finding("webhook_abuse", "medium", actor="1.2.3.4",
                           evidence={"count": 12, "threshold": 5})
        performed = sum(len(engine.defend([finding]).actions_performed) for _ in range(5))
        assert performed == 1

    def test_every_decision_is_recorded(self):
        engine, log, _ = _engine()
        engine.defend([_finding("auth_bruteforce", "medium", actor="a",
                                evidence={"count": 12, "threshold": 5})])
        assert log.count("defence") >= 1
        assert log.verify()["ok"] is True


# ---------------------------------------------------------------------------
# 10. Hard prohibitions
# ---------------------------------------------------------------------------

class TestHardProhibitions:
    @pytest.mark.parametrize("action", sorted(NEVER_ACTIONS))
    def test_never_actions_are_never_performed(self, action):
        engine, _, _ = _engine()
        assert engine.catalog.allowed(action) is False

    def test_guardian_cannot_change_its_own_authority(self):
        # The engine exposes no method that grants permission or changes policy.
        engine, _, _ = _engine()
        for name in dir(engine):
            assert "grant" not in name.lower()
            assert "set_policy" not in name.lower()
            assert "change_authority" not in name.lower()

    def test_defence_report_serialisable(self):
        engine, _, _ = _engine()
        rep = engine.defend([_finding("auth_bruteforce", "medium", actor="a",
                                      evidence={"count": 12, "threshold": 5})])
        json.dumps(rep.to_dict())

    def test_severity_rank_is_ordered(self):
        assert SEVERITY_RANK["critical"] > SEVERITY_RANK["high"] > SEVERITY_RANK["medium"]
        assert SEVERITY_RANK["medium"] > SEVERITY_RANK["low"] > SEVERITY_RANK["info"]
