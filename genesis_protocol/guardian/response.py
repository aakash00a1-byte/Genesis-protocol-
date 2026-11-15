"""Defensive response recommendations for the AI Guardian (V7 P5).

The guardian is **read-only**. It detects, classifies, alerts and records - and
then *recommends* a response. It never carries one out.

Hard rules, enforced here:

* Every recommendation is a proposal with an explicit ``reversible`` flag and a
  ``rollback`` description. Nothing is executed.
* Privileged responses (suspend/revoke an identity, revoke a credential, rotate a
  secret, block a network source) are always marked
  ``requires_owner_approval=True`` and ``automatic=False``.
* A fixed set of actions is **never** recommended for autonomous execution:
  account deletion, credential rotation, code modification, deployment, settings
  changes, permission grants. These are refused outright by
  :meth:`DefensiveResponder.recommend` - see :data:`FORBIDDEN_ACTIONS`.
* Recommendations preserve the evidence that produced them, so a human can
  review before approving.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Actions the guardian will never propose as an autonomous response. Attempting
# to build one raises, so the guarantee cannot be lost by a careless edit.
FORBIDDEN_ACTIONS = frozenset({
    "delete_account",
    "rotate_credential",
    "modify_code",
    "deploy",
    "change_settings",
    "grant_permission",
    "push_main",
})

# Actions that touch security state and therefore always need owner approval.
PRIVILEGED_ACTIONS = frozenset({
    "suspend_identity",
    "revoke_identity",
    "revoke_credential",
    "rotate_secret",
    "block_source",
    "require_owner_review",
})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResponseRecommendation:
    """A proposed, reversible response. Never an action taken."""

    action: str
    target: Optional[str]
    rationale: str
    reversible: bool
    rollback: str
    requires_owner_approval: bool
    automatic: bool = False
    evidence: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DefensiveResponder:
    """Turns findings into reversible, owner-gated recommendations."""

    # -- mapping --------------------------------------------------------------

    # detector -> (action, target_from, rationale, reversible, rollback)
    _CATALOG: Dict[str, tuple] = {
        "auth_bruteforce": (
            "require_owner_review", "actor",
            "repeated authentication failures suggest a credential-stuffing attempt",
            True, "no state changed; the recommendation only asks for a review",
        ),
        "webhook_abuse": (
            "block_source", "actor",
            "a source repeatedly sent invalid or rejected webhook calls",
            True, "unblock the source; no data is deleted",
        ),
        "api_burst": (
            "require_owner_review", "actor",
            "unusual API volume from one actor warrants a look",
            True, "no state changed",
        ),
        "identity_spoofing": (
            "suspend_identity", "subject",
            "an agent identity appears in the audit but does not verify",
            True, "reactivate the identity after review",
        ),
        "privilege_escalation": (
            "require_owner_review", "actor",
            "a privileged operation was attempted and denied",
            True, "no state changed",
        ),
        "repeated_denials": (
            "require_owner_review", "actor",
            "the same actor repeatedly attempted denied actions",
            True, "no state changed",
        ),
        "secret_exposure": (
            "rotate_secret", "actor",
            "a secret-shaped value appeared in a runtime payload",
            True, "the rotation is reversible only by the owner; the guardian does not perform it",
        ),
        "unregistered_tool": (
            "require_owner_review", "subject",
            "a tool ran that is not in the registry",
            True, "no state changed",
        ),
        "execution_after_denial": (
            "suspend_identity", "actor",
            "a tool produced a result after its request was denied",
            True, "reactivate the identity after review",
        ),
        "grant_escape": (
            "suspend_identity", "agent_id",
            "an agent requested tools outside its declared grant",
            True, "reactivate the identity after review",
        ),
        "policy_violation": (
            "require_owner_review", "agent_id",
            "an agent made policy-denied requests",
            True, "no state changed",
        ),
        "unusual_tool_variety": (
            "require_owner_review", "agent_id",
            "an agent used an unusually wide range of tools",
            True, "no state changed",
        ),
        "repeated_denied_actions": (
            "require_owner_review", "agent_id",
            "an agent repeatedly attempted denied actions",
            True, "no state changed",
        ),
    }

    # -- build ----------------------------------------------------------------

    def recommend(self, finding: Any) -> Optional[ResponseRecommendation]:
        """Map one finding (dict or object with ``to_dict``) to a recommendation.

        Informational findings (``severity == "info"``) produce no recommendation:
        there is nothing to respond to, and recommending a review for a healthy
        signal is exactly the false positive this layer must avoid.
        """
        data = finding.to_dict() if hasattr(finding, "to_dict") else dict(finding)
        if str(data.get("severity") or "").lower() == "info":
            return None
        detector = str(data.get("detector") or "")
        entry = self._CATALOG.get(detector)
        if entry is None:
            # An unknown finding still yields a review recommendation, never an action.
            entry = ("require_owner_review", "actor",
                     "unrecognised finding; a human should review it",
                     True, "no state changed")
        action, target_key, rationale, reversible, rollback = entry
        if action in FORBIDDEN_ACTIONS:
            raise ValueError(f"refusing to recommend forbidden action '{action}'")
        target = data.get(target_key) or data.get("actor") or data.get("subject") or data.get("agent_id")
        return ResponseRecommendation(
            action=action,
            target=target,
            rationale=rationale,
            reversible=reversible,
            rollback=rollback,
            requires_owner_approval=action in PRIVILEGED_ACTIONS,
            automatic=False,
            evidence={k: data.get(k) for k in ("detector", "severity", "title", "description", "evidence")
                      if data.get(k) is not None},
        )

    def recommend_many(self, findings: List[Any]) -> List[ResponseRecommendation]:
        out = []
        for finding in findings:
            rec = self.recommend(finding)
            if rec is not None:
                out.append(rec)
        return out

    @staticmethod
    def is_reversible_only(recommendations: List[ResponseRecommendation]) -> bool:
        """Whether every recommendation is reversible and non-automatic."""
        return all(r.reversible and not r.automatic for r in recommendations)
