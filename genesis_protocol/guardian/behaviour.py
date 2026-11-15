"""Agent behaviour monitoring for the AI Guardian (V7 P5).

Watches how agents behave over their audited history: unusual tool-call patterns,
policy violations, repeated denied actions, and whether an agent's identity is
consistent with that history.

It composes the existing authorities:

* ``agentic.audit.AuditLog`` - the agent's own action history.
* ``agentic.identity_registry.IdentityRegistry`` - who the agent is, its grants,
  its status, its parentage.
* ``agentic.trust.TrustEvaluator`` - the evidence-based trust level (a
  *description* of the record, never a permission).

Distinct from :mod:`genesis_protocol.guardian.detection`, which looks at a single
event stream; this module reasons about *per-agent patterns over time*.

Read-only. Every finding states the evidence that produced it. No finding
changes an agent's grants, status or trust.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from genesis_protocol.agentic.audit import AuditLog, get_audit_log

# Behavioural thresholds. Named so firing conditions are reviewable.
TOOL_VARIETY_THRESHOLD = 8      # distinct tools used by one agent in a window
RESTRICTED_RATIO_THRESHOLD = 0.5  # share of an agent's calls that are restricted
GRANT_ESCAPE_THRESHOLD = 1      # calls outside the agent's declared grant


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class BehaviourFinding:
    """One behavioural observation with its supporting evidence."""

    detector: str
    severity: str
    agent_id: str
    title: str
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    detected_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BehaviourMonitor:
    """Per-agent behavioural analysis over the audited history."""

    def __init__(
        self,
        audit: Optional[AuditLog] = None,
        identity_registry: Optional[Any] = None,
        trust_evaluator: Optional[Any] = None,
    ):
        self.audit = audit or get_audit_log()
        self._identities = identity_registry
        self._trust = trust_evaluator

    @property
    def identities(self) -> Any:
        if self._identities is None:
            from genesis_protocol.agentic.identity_registry import get_identity_registry

            self._identities = get_identity_registry()
        return self._identities

    @property
    def trust(self) -> Any:
        if self._trust is None:
            from genesis_protocol.agentic.trust import get_trust_evaluator

            self._trust = get_trust_evaluator()
        return self._trust

    # -- history --------------------------------------------------------------

    def history_for(self, agent_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Audit entries mentioning ``agent_id`` (best effort)."""
        try:
            return [e for e in self.audit.tail(limit) if e.get("agent_id") == agent_id]
        except Exception:
            return []

    # -- detectors ------------------------------------------------------------

    def detect_unusual_tool_patterns(
        self, agent_id: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> List[BehaviourFinding]:
        history = history if history is not None else self.history_for(agent_id)
        results = [e for e in history if e.get("event") == "tool_result"]
        tools = [str(e.get("tool")) for e in results if e.get("tool")]
        distinct = sorted(set(tools))
        findings = []
        if len(distinct) >= TOOL_VARIETY_THRESHOLD:
            findings.append(BehaviourFinding(
                detector="unusual_tool_variety", severity="medium", agent_id=agent_id,
                title=f"agent '{agent_id}' used an unusually wide range of tools",
                description=f"{len(distinct)} distinct tools used, above the expected variety",
                evidence={"distinct_tools": distinct, "threshold": TOOL_VARIETY_THRESHOLD},
                confidence=0.6,
            ))
        return findings

    def detect_policy_violations(
        self, agent_id: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> List[BehaviourFinding]:
        history = history if history is not None else self.history_for(agent_id)
        denied = [e for e in history if e.get("event") in ("tool_request", "skill_tool_request")
                  and e.get("allowed") is False]
        findings = []
        if denied:
            findings.append(BehaviourFinding(
                detector="policy_violation", severity="medium", agent_id=agent_id,
                title=f"agent '{agent_id}' made policy-denied requests",
                description=f"{len(denied)} requests were denied by policy",
                evidence={"denied_count": len(denied),
                          "reasons": sorted({str(e.get("reason")) for e in denied})[:5]},
                confidence=0.75,
            ))
        return findings

    def detect_repeated_denials(
        self, agent_id: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> List[BehaviourFinding]:
        history = history if history is not None else self.history_for(agent_id)
        denied = [e for e in history if e.get("allowed") is False]
        findings = []
        if len(denied) >= 3:
            findings.append(BehaviourFinding(
                detector="repeated_denied_actions", severity="high", agent_id=agent_id,
                title=f"agent '{agent_id}' repeatedly attempted denied actions",
                description=f"{len(denied)} denied actions recorded for this agent",
                evidence={"denied_count": len(denied)}, confidence=0.8,
            ))
        return findings

    def detect_grant_escape(
        self, agent_id: str, history: Optional[List[Dict[str, Any]]] = None
    ) -> List[BehaviourFinding]:
        """Calls to tools outside the agent's declared grant."""
        identity = self.identities.get(agent_id)
        if identity is None or not identity.tools:
            return []
        history = history if history is not None else self.history_for(agent_id)
        outside = sorted({
            str(e.get("tool")) for e in history
            if e.get("tool") and e.get("event") == "tool_request" and str(e.get("tool")) not in identity.tools
        })
        if len(outside) >= GRANT_ESCAPE_THRESHOLD:
            return [BehaviourFinding(
                detector="grant_escape", severity="high", agent_id=agent_id,
                title=f"agent '{agent_id}' requested tools outside its grant",
                description="requests were made for tools not in the agent's declared grant",
                evidence={"outside_grant": outside, "grant": list(identity.tools)},
                confidence=0.85,
            )]
        return []

    # -- correlation ----------------------------------------------------------

    def correlate(self, agent_id: str) -> Dict[str, Any]:
        """Correlate an agent's identity, trust and history into one view."""
        identity = self.identities.get(agent_id)
        verification = self.identities.verify(agent_id)
        history = self.history_for(agent_id)
        trust = None
        if identity is not None:
            try:
                trust = self.trust.evaluate(identity, history=history).to_dict()
            except Exception:
                trust = None
        success_events = ("tool_result", "skill_tool_result")
        successes = sum(1 for e in history if e.get("event") in success_events and e.get("allowed") is True)
        denials = sum(1 for e in history if e.get("allowed") is False)
        return {
            "agent_id": agent_id,
            "identity": identity.to_dict() if identity is not None else None,
            "verification": verification.to_dict(),
            "trust": trust,
            "history_size": len(history),
            "successes": successes,
            "denials": denials,
            "timeline": sorted(
                [{"ts": e.get("ts"), "event": e.get("event"), "tool": e.get("tool"),
                  "allowed": e.get("allowed"), "reason": e.get("reason")} for e in history],
                key=lambda r: r.get("ts") or "",
            ),
        }

    # -- entry point ----------------------------------------------------------

    def monitor(self, agent_ids: Optional[Iterable[str]] = None) -> List[BehaviourFinding]:
        """Run every detector for the given agents (or all known agents)."""
        if agent_ids is None:
            try:
                agent_ids = [a.agent_id for a in self.identities.list_agents()]
            except Exception:
                agent_ids = []
            # Also cover agent ids that only appear in the audit log.
            try:
                agent_ids = sorted(set(agent_ids) | {
                    str(e.get("agent_id")) for e in self.audit.tail(1000) if e.get("agent_id")
                })
            except Exception:
                pass
        findings: List[BehaviourFinding] = []
        for agent_id in agent_ids:
            history = self.history_for(agent_id)
            findings += self.detect_unusual_tool_patterns(agent_id, history)
            findings += self.detect_policy_violations(agent_id, history)
            findings += self.detect_repeated_denials(agent_id, history)
            findings += self.detect_grant_escape(agent_id, history)
        return findings
