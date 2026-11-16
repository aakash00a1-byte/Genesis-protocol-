"""Allow-list of defensive actions and their risk classification (V7 P6).

Only actions named here may ever be performed by the guardian, and only those
whose ``risk == "low"`` may be performed automatically. Everything else is
proposed to the owner.

The list is intentionally tiny and every entry is **reversible** with a stated
rollback. There is no entry for deleting data, rotating a credential, editing
code, deploying, changing a trust root, changing a permission threshold or
altering the guardian's own authority - those are not defensive actions, they
are the forbidden set in :mod:`genesis_protocol.guardian.response`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

# Risk levels for defensive actions.
LOW = "low"
MEDIUM = "medium"
HIGH = "high"


@dataclass(frozen=True)
class ActionSpec:
    """A permitted defensive action and the safety properties it must satisfy."""

    action: str
    risk: str
    reversible: bool
    rollback: str
    description: str
    automatic_allowed: bool = False

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


# The complete allow-list. Anything not present is refused by the policy engine.
ALLOWED_ACTIONS: Dict[str, ActionSpec] = {
    # Low-risk, automatic, and genuinely reversible: appends a request to a
    # rate-limit ledger, which only ever *narrows* what an actor may do next and
    # expires on its own. It touches no identity, credential or permission.
    "rate_limit_actor": ActionSpec(
        action="rate_limit_actor",
        risk=LOW,
        reversible=True,
        rollback="the ledger entry expires after the cooldown; no state is destroyed",
        description="apply a temporary cooldown to one actor's requests",
        automatic_allowed=True,
    ),
    "throttle_source": ActionSpec(
        action="throttle_source",
        risk=LOW,
        reversible=True,
        rollback="the throttle entry expires after the cooldown",
        description="apply a temporary cooldown to one network source",
        automatic_allowed=True,
    ),
    "raise_alert": ActionSpec(
        action="raise_alert",
        risk=LOW,
        reversible=True,
        rollback="an alert is informational; nothing to roll back",
        description="raise an owner alert for a confirmed incident",
        automatic_allowed=True,
    ),
    # Medium/high risk: proposed only, never automatic.
    "require_owner_review": ActionSpec(
        action="require_owner_review",
        risk=MEDIUM,
        reversible=True,
        rollback="no state changed",
        description="flag the incident for owner review",
    ),
    "suspend_identity": ActionSpec(
        action="suspend_identity",
        risk=HIGH,
        reversible=True,
        rollback="reactivate the identity via the IdentityRegistry",
        description="suspend an agent identity (owner approval required)",
    ),
    "revoke_credential": ActionSpec(
        action="revoke_credential",
        risk=HIGH,
        reversible=True,
        rollback="issue a fresh short-lived credential to the agent",
        description="revoke an agent's short-lived credential (owner approval required)",
    ),
    "rotate_secret": ActionSpec(
        action="rotate_secret",
        risk=HIGH,
        reversible=True,
        rollback="the owner performs the rotation; the guardian never does",
        description="request owner rotation of a suspected-exposed secret",
    ),
}

# Actions the guardian must never perform, whatever the evidence. Kept here as
# well as in response.py so the policy engine fails closed even if called with a
# hand-built action name.
NEVER_ACTIONS = frozenset({
    "delete_account",
    "delete_data",
    "rotate_credential",
    "modify_code",
    "deploy",
    "change_settings",
    "change_trust_root",
    "change_permission_threshold",
    "grant_permission",
    "change_own_authority",
    "push_main",
    "disable_safety",
    "disable_audit",
})


class ActionNotAllowed(ValueError):
    """Raised when an action is not on the allow-list."""


class ActionCatalog:
    """Looks up permitted actions and answers safety questions about them."""

    def __init__(self, specs: Optional[Dict[str, ActionSpec]] = None):
        self._specs = dict(specs if specs is not None else ALLOWED_ACTIONS)

    def get(self, action: str) -> Optional[ActionSpec]:
        return self._specs.get(action)

    def allowed(self, action: str) -> bool:
        return action in self._specs and action not in NEVER_ACTIONS

    def require(self, action: str) -> ActionSpec:
        if action in NEVER_ACTIONS or action not in self._specs:
            raise ActionNotAllowed(f"action '{action}' is not a permitted defensive action")
        return self._specs[action]

    def is_automatic_allowed(self, action: str) -> bool:
        spec = self.get(action)
        return bool(spec and spec.automatic_allowed and spec.risk == LOW and spec.reversible
                    and action not in NEVER_ACTIONS)

    def all_specs(self) -> List[Dict[str, object]]:
        return [s.to_dict() for s in self._specs.values()]
