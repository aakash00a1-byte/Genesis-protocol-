"""Secure agent delegation (V7 P10).

Delegation hands a mission task to a *specific, verified* agent identity with a
*narrowed* tool grant. It reuses the canonical identity system rather than
inventing a second one:

* the delegate must exist, be active, and pass ``IdentityRegistry.verify``;
* the tools it is allowed to use must be a subset of the delegator's grant
  (privilege can only narrow down the tree);
* a delegation is recorded with its scope so it can be audited and revoked.

When no identity registry is configured the manager falls back to a fail-closed
*local* check: a delegation to an unknown agent is refused.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DelegationRefused(RuntimeError):
    """Raised when a delegation is unsafe or unverifiable."""


@dataclass
class Delegation:
    delegation_id: str
    task_id: str
    agent_id: str
    tools: List[str] = field(default_factory=list)
    granted_at: str = field(default_factory=utcnow)
    status: str = "active"  # active | revoked
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DelegationManager:
    """Grants bounded, verifiable work to agent identities."""

    def __init__(self, registry: Optional[Any] = None):
        self._registry = registry
        self._delegations: Dict[str, Delegation] = {}
        self._counter = 0

    @property
    def registry(self) -> Any:
        if self._registry is None:
            try:
                from genesis_protocol.agentic.identity_registry import get_identity_registry

                self._registry = get_identity_registry()
            except Exception:
                self._registry = None
        return self._registry

    def _identity_tools(self, agent_id: str) -> Optional[Set[str]]:
        reg = self.registry
        if reg is None:
            return None
        identity = reg.get(agent_id)
        if identity is None:
            return None
        return set(identity.tools or ())

    def delegate(
        self,
        task_id: str,
        agent_id: str,
        tools: Iterable[str] = (),
        delegator_id: Optional[str] = None,
        credential: Optional[str] = None,
    ) -> Delegation:
        """Delegate a task to a verified agent with a narrowed tool grant."""
        reg = self.registry
        if reg is None or not hasattr(reg, "verify") or not hasattr(reg, "get"):
            raise DelegationRefused("no identity registry is configured; refusing to delegate")

        verification = reg.verify(agent_id, credential)
        if not verification.ok:
            raise DelegationRefused(f"delegate not verified: {verification.reason}")

        allowed = self._identity_tools(agent_id) or set()
        requested = {str(t).strip() for t in tools if str(t).strip()}
        over = requested - allowed
        if over:
            raise DelegationRefused(
                "delegation would exceed the agent's grant: " + ", ".join(sorted(over))
            )

        if delegator_id:
            parent_allowed = self._identity_tools(delegator_id)
            if parent_allowed is None:
                raise DelegationRefused(f"delegator '{delegator_id}' is unknown")
            over_parent = requested - parent_allowed
            if over_parent:
                raise DelegationRefused(
                    "delegation exceeds the delegator's grant: " + ", ".join(sorted(over_parent))
                )

        self._counter += 1
        delegation = Delegation(
            delegation_id=f"del-{self._counter}",
            task_id=task_id,
            agent_id=agent_id,
            tools=sorted(requested),
            reason="verified",
        )
        self._delegations[delegation.delegation_id] = delegation
        return delegation

    def revoke(self, delegation_id: str, reason: str = "") -> Delegation:
        delegation = self._delegations.get(delegation_id)
        if delegation is None:
            raise DelegationRefused(f"unknown delegation '{delegation_id}'")
        delegation.status = "revoked"
        delegation.reason = reason or "revoked"
        return delegation

    def for_task(self, task_id: str) -> List[Delegation]:
        return [d for d in self._delegations.values() if d.task_id == task_id]

    def list(self) -> List[Delegation]:
        return list(self._delegations.values())
