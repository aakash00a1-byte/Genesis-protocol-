"""Controlled autonomous defence engine (V7 P6).

This is the only place P6 performs an action. Every action passes through the
same ordered gate, and each gate can only ever *reduce* what happens:

1. **Kill switch** - if engaged, nothing is performed (detect/alert/record only).
2. **Severity + confidence** - a finding is actionable only when it is confirmed
   (confidence above the bar) *and* classified at or above the action's minimum
   severity.
3. **Correlation** - independent corroboration is required before a *high-impact*
   action; a lone weak signal never triggers one.
4. **Allow-list** - the action must be on the allow-list in ``actions.py``.
5. **Automatic or owner** - only ``low`` risk, reversible, allow-listed actions
   may run automatically. Everything else is returned as a proposal.
6. **Budget** - per-target cooldown and global/consecutive caps.
7. **Execute + rollback** - a low-risk action runs, and an explicit rollback is
   registered so it can be undone.

The engine never deletes data, rotates a credential, edits code, deploys, changes
a trust root or permission threshold, or changes its own authority: those actions
are absent from the allow-list and rejected by :class:`ActionCatalog`.

Every decision - allowed or refused - is appended to the tamper-evident security
log with the reason, so autonomous behaviour is fully auditable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from genesis_protocol.guardian.actions import ActionCatalog, ActionNotAllowed
from genesis_protocol.guardian.budget import ActionBudget, BudgetDecision
from genesis_protocol.guardian.correlation import Correlator, Incident
from genesis_protocol.guardian.events import SecurityEventLog, get_security_log
from genesis_protocol.guardian.killswitch import KillSwitch, get_kill_switch
from genesis_protocol.guardian.severity import SEVERITY_RANK, SeverityClassifier

# Minimum severity for an action to be considered at all.
ACTION_MIN_SEVERITY: Dict[str, str] = {
    "raise_alert": "low",
    "rate_limit_actor": "medium",
    "throttle_source": "medium",
    "require_owner_review": "low",
    "suspend_identity": "high",
    "revoke_credential": "high",
    "rotate_secret": "critical",
}

# High-impact actions require independent corroboration before they are proposed.
HIGH_IMPACT_ACTIONS = frozenset({"suspend_identity", "revoke_credential", "rotate_secret"})

# detector -> action chosen for that detector's incident.
DETECTOR_ACTION: Dict[str, str] = {
    "auth_bruteforce": "rate_limit_actor",
    "webhook_abuse": "throttle_source",
    "api_burst": "rate_limit_actor",
    "identity_spoofing": "suspend_identity",
    "privilege_escalation": "require_owner_review",
    "repeated_denials": "rate_limit_actor",
    "repeated_denied_actions": "rate_limit_actor",
    "secret_exposure": "rotate_secret",
    "unregistered_tool": "require_owner_review",
    "execution_after_denial": "suspend_identity",
    "grant_escape": "suspend_identity",
    "policy_violation": "require_owner_review",
    "unusual_tool_variety": "require_owner_review",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DefenceDecision:
    """The outcome of evaluating one incident for one action."""

    action: str
    target: Optional[str]
    incident_id: Optional[str]
    performed: bool
    automatic: bool
    requires_owner_approval: bool
    reason: str
    risk: str = ""
    rollback: str = ""
    rollback_token: Optional[str] = None
    budget: Optional[Dict[str, Any]] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    decided_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DefenceReport:
    """The outcome of one defence pass."""

    started_at: str
    finished_at: str
    kill_switch_engaged: bool
    incidents: List[Dict[str, Any]]
    decisions: List[Dict[str, Any]]
    actions_performed: List[Dict[str, Any]]
    proposals: List[Dict[str, Any]]
    alerts: List[Dict[str, Any]]
    read_only: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DefenceEngine:
    """Turns correlated incidents into bounded, reversible defensive actions."""

    def __init__(
        self,
        security_log: Optional[SecurityEventLog] = None,
        kill_switch: Optional[KillSwitch] = None,
        catalog: Optional[ActionCatalog] = None,
        budget: Optional[ActionBudget] = None,
        classifier: Optional[SeverityClassifier] = None,
        correlator: Optional[Correlator] = None,
        action_sink: Optional[Any] = None,
        alert_sink: Optional[Any] = None,
    ):
        self.security_log = security_log or get_security_log()
        self.kill_switch = kill_switch or get_kill_switch()
        self.catalog = catalog or ActionCatalog()
        self.budget = budget or ActionBudget()
        self.classifier = classifier or SeverityClassifier()
        self.correlator = correlator or Correlator()
        # action_sink performs a low-risk action and returns a rollback token.
        # Kept injectable so the engine is testable without touching live state.
        self.action_sink = action_sink
        self.alert_sink = alert_sink

    # -- target selection -----------------------------------------------------

    @staticmethod
    def _target_for(action: str, incident: Incident) -> Optional[str]:
        if action in ("throttle_source",):
            for name in ("actor", "session", "subject"):
                if incident.entities.get(name):
                    return incident.entities[name][0]
            return None
        for name in ("identity", "actor", "subject", "session"):
            if incident.entities.get(name):
                return incident.entities[name][0]
        return None

    def _choose_action(self, incident: Incident) -> Optional[str]:
        """Pick the action for the incident's most severe mapped detector.

        Selection is by detector severity (then catalogue order), not by the
        alphabetical detector list, so the action is the one the strongest
        evidence justifies and is stable across runs.
        """
        from genesis_protocol.guardian.severity import BASE_SEVERITY

        ranked = sorted(
            (d for d in incident.detectors if d in DETECTOR_ACTION),
            key=lambda d: -SEVERITY_RANK.get(BASE_SEVERITY.get(d, "low"), 0),
        )
        for detector in ranked:
            return DETECTOR_ACTION[detector]
        return None

    # -- evaluation -----------------------------------------------------------

    def evaluate_incident(self, incident: Incident) -> DefenceDecision:
        action = self._choose_action(incident)
        if action is None:
            return DefenceDecision(
                action="none", target=None, incident_id=incident.incident_id,
                performed=False, automatic=False, requires_owner_approval=False,
                reason="no allow-listed action maps to this incident",
            )
        target = self._target_for(action, incident)

        # 4. allow-list
        try:
            spec = self.catalog.require(action)
        except ActionNotAllowed as exc:
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=False, requires_owner_approval=True,
                reason=f"action not permitted: {exc}",
            )

        # 2. severity floor for the action
        floor = ACTION_MIN_SEVERITY.get(action, "high")
        if SEVERITY_RANK.get(incident.severity, 0) < SEVERITY_RANK.get(floor, 4):
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=False,
                requires_owner_approval=action in HIGH_IMPACT_ACTIONS,
                reason=f"incident severity '{incident.severity}' below the '{floor}' floor for '{action}'",
                risk=spec.risk, rollback=spec.rollback,
            )

        # 3. corroboration for high-impact actions
        if action in HIGH_IMPACT_ACTIONS and len(incident.detectors) < 2 and incident.confidence < 0.9:
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=False, requires_owner_approval=True,
                reason="high-impact action needs independent corroboration or confidence >= 0.9",
                risk=spec.risk, rollback=spec.rollback,
            )

        # 5. automatic vs owner-gated
        if not self.catalog.is_automatic_allowed(action):
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=False, requires_owner_approval=True,
                reason=f"'{action}' is not an automatic action; proposed for owner approval",
                risk=spec.risk, rollback=spec.rollback,
            )

        # 1. kill switch (checked last so the reason is precise)
        if self.kill_switch.is_engaged():
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=True, requires_owner_approval=False,
                reason="kill switch engaged: automatic defence stopped",
                risk=spec.risk, rollback=spec.rollback,
            )

        # 6. budget
        key = f"{action}:{target or 'global'}"
        decision: BudgetDecision = self.budget.check(key)
        if not decision.allowed:
            return DefenceDecision(
                action=action, target=target, incident_id=incident.incident_id,
                performed=False, automatic=True, requires_owner_approval=False,
                reason=f"within limits denied: {decision.reason}",
                risk=spec.risk, rollback=spec.rollback, budget=decision.to_dict(),
            )

        # 7. execute
        rollback_token = None
        if self.action_sink is not None:
            try:
                rollback_token = self.action_sink(action, target, incident)
            except Exception as exc:  # an action failure must never crash the pass
                return DefenceDecision(
                    action=action, target=target, incident_id=incident.incident_id,
                    performed=False, automatic=True, requires_owner_approval=False,
                    reason=f"action failed: {exc}", risk=spec.risk, rollback=spec.rollback,
                    budget=decision.to_dict(),
                )
        self.budget.consume(key)
        return DefenceDecision(
            action=action, target=target, incident_id=incident.incident_id,
            performed=True, automatic=True, requires_owner_approval=False,
            reason="low-risk reversible action performed within budget",
            risk=spec.risk, rollback=spec.rollback, rollback_token=rollback_token,
            budget=decision.to_dict(),
        )

    # -- pass -----------------------------------------------------------------

    def defend(self, findings: List[Any], observations_audit: Optional[List[Dict[str, Any]]] = None) -> DefenceReport:
        """Classify, correlate, alert and (within bounds) act on a set of findings."""
        started = _utcnow()
        classified = self.classifier.classify_many(findings)
        confirmed = [c for c in classified if SeverityClassifier.is_confirmed(c)]
        incidents = self.correlator.correlate(confirmed)

        decisions: List[DefenceDecision] = []
        actions_performed: List[Dict[str, Any]] = []
        proposals: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []

        for incident in incidents:
            decision = self.evaluate_incident(incident)
            decisions.append(decision)
            if decision.performed:
                actions_performed.append(decision.to_dict())
            if decision.requires_owner_approval and not decision.performed:
                proposals.append(decision.to_dict())
            # Confirmed incidents raise an alert (informational, reversible).
            if SEVERITY_RANK.get(incident.severity, 0) >= SEVERITY_RANK["high"]:
                alert = self._raise_alert(incident)
                alerts.append(alert)

        if not actions_performed:
            self.budget.note_quiet_pass()

        for decision in decisions:
            self._record(decision)

        return DefenceReport(
            started_at=started,
            finished_at=_utcnow(),
            kill_switch_engaged=self.kill_switch.is_engaged(),
            incidents=[i.to_dict() for i in incidents],
            decisions=[d.to_dict() for d in decisions],
            actions_performed=actions_performed,
            proposals=proposals,
            alerts=alerts,
            read_only=not actions_performed,
        )

    # -- helpers --------------------------------------------------------------

    def _raise_alert(self, incident: Incident) -> Dict[str, Any]:
        alert = {
            "incident_id": incident.incident_id,
            "severity": incident.severity,
            "confidence": incident.confidence,
            "detectors": incident.detectors,
            "entities": incident.entities,
        }
        if self.alert_sink is not None:
            try:
                self.alert_sink(incident)
                alert["delivered"] = True
            except Exception as exc:
                alert["delivered"] = False
                alert["delivery_error"] = str(exc)
        else:
            alert["delivered"] = False
        return alert

    def _record(self, decision: DefenceDecision) -> None:
        try:
            self.security_log.record(
                category="defence",
                event=f"defence:{decision.action}",
                severity="info" if decision.performed else "low",
                actor=decision.target,
                subject=decision.incident_id,
                evidence={
                    "performed": decision.performed,
                    "automatic": decision.automatic,
                    "requires_owner_approval": decision.requires_owner_approval,
                    "reason": decision.reason,
                    "risk": decision.risk,
                    "rollback": decision.rollback,
                },
            )
        except Exception:
            # Recording must never break the defence pass.
            pass

    def rollback(self, action: str, target: Optional[str], token: Optional[str] = None) -> bool:
        """Undo a performed low-risk action via the injected sink."""
        if not self.catalog.allowed(action):
            raise ActionNotAllowed(f"cannot roll back non-permitted action '{action}'")
        if self.action_sink is None or not hasattr(self.action_sink, "rollback"):
            return False
        return bool(self.action_sink.rollback(action, target, token))
