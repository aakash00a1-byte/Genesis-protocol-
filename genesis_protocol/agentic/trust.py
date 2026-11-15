"""Evidence-based trust levels for GLUTEN agents.

Trust here is a *description* of an agent's recorded track record, never a
permission. It is computed only from evidence the system already holds - the
agent's identity, its grants, its credential hygiene and its audited outcomes -
and it can never grant an action. The boundary guard (``agentic.boundaries``)
and the fail-closed policy remain the only things that allow or deny a call.

The level is one of ``untrusted`` < ``provisional`` < ``trusted`` < ``verified``.
The two hard caps matter:

* A revoked or suspended identity is always ``untrusted``, whatever its history.
* An agent whose recorded failures exceed its successes cannot exceed
  ``provisional``.

Every level is reported with the evidence that produced it, so a level is never
an opaque number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.audit import AuditLog, get_audit_log
from genesis_protocol.agentic.identity_registry import AgentIdentity

TRUST_LEVELS = ("untrusted", "provisional", "trusted", "verified")

# Outcomes that count as evidence of reliability.
_SUCCESS_EVENTS = {
    "tool_result": True,
    "skill_tool_result": True,
    "tool_request": True,
}
_DENIED_EVENTS = {"tool_request"}


@dataclass
class TrustReport:
    """A trust level with the evidence behind it."""

    agent_id: str
    level: str
    score: int
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "level": self.level,
            "score": self.score,
            "evidence": self.evidence,
        }


class TrustEvaluator:
    """Computes evidence-based trust for agents. Never grants permission."""

    def __init__(self, audit: Optional[AuditLog] = None):
        self.audit = audit or get_audit_log()

    def evaluate(self, identity: AgentIdentity, history: Optional[List[Dict[str, Any]]] = None) -> TrustReport:
        """Score ``identity`` from its audited history.

        ``history`` may be supplied (a list of audit entries for this agent);
        otherwise the audit log is read.
        """
        if history is None:
            history = self._history_for(identity.agent_id)

        successes = 0
        failures = 0
        denials = 0
        for entry in history:
            event = entry.get("event")
            allowed = entry.get("allowed")
            if event in _SUCCESS_EVENTS and allowed is True:
                successes += 1
            elif event in _SUCCESS_EVENTS and allowed is False:
                if event in _DENIED_EVENTS:
                    denials += 1
                else:
                    failures += 1

        evidence = {
            "successes": successes,
            "failures": failures,
            "denials": denials,
            "status": identity.status,
            "grant_size": len(identity.tools),
            "has_parent": identity.parent_id is not None,
            "owner_bound": identity.owner_id is not None,
            "provider_bound": identity.provider is not None,
        }

        # Hard caps first: no amount of history overrides a dead identity.
        if identity.status != "active":
            return TrustReport(identity.agent_id, "untrusted", 0, evidence)

        score = successes * 2 - failures - denials
        score = max(score, 0)

        if successes == 0:
            level = "provisional" if identity.owner_id is not None else "untrusted"
        elif failures > successes:
            level = "provisional"  # never above provisional with a poor record
        elif score >= 10 and successes >= 5:
            level = "verified"
        elif score >= 4 and successes >= 2:
            level = "trusted"
        else:
            level = "provisional"

        return TrustReport(identity.agent_id, level, score, evidence)

    def _history_for(self, agent_id: str) -> List[Dict[str, Any]]:
        """Audit entries mentioning ``agent_id`` (best effort, newest first)."""
        try:
            entries = self.audit.tail(1000)
        except Exception:
            return []
        return [e for e in entries if e.get("agent_id") == agent_id]


_default: Optional[TrustEvaluator] = None


def get_trust_evaluator() -> TrustEvaluator:
    global _default
    if _default is None:
        _default = TrustEvaluator()
    return _default
