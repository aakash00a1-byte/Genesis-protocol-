"""Consistent authorization across every interface (V7 P7).

Telegram, GitHub, the web UI and Gluten each arrive with a different notion of
"who is calling". This module maps every interface to the one canonical policy:

* it resolves an interface-specific principal (a Telegram user id, a web session
  user id, a GitHub actor, a Gluten actor) to a Genesis principal;
* it answers authorization questions by delegating to ``AgentPolicy`` and the
  ``CapabilityRegistry`` - it never decides on its own;
* it fails closed: an interface it does not recognise, or a principal it cannot
  resolve, is denied.

The point is that the *same* request is allowed or denied identically no matter
which interface it came from, because every interface ends up calling the same
``authorize`` here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

KNOWN_INTERFACES = frozenset({"telegram", "github", "web", "gluten", "api", "cli"})


@dataclass
class InterfaceDecision:
    allowed: bool
    reason: str
    interface: str
    principal: Optional[str] = None
    requires_owner_approval: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InterfaceAuthorizer:
    """Resolves interface principals and answers via the canonical policy."""

    def __init__(self, policy: Optional[Any] = None, registry: Optional[Any] = None,
                 owner_ids: Optional[set] = None):
        self._policy = policy
        self._registry = registry
        self._owner_ids = owner_ids

    @property
    def policy(self) -> Any:
        if self._policy is None:
            from genesis_protocol.agentic.policy import get_agent_policy

            self._policy = get_agent_policy()
        return self._policy

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from genesis_protocol.coordination.registry import CapabilityRegistry

            self._registry = CapabilityRegistry()
        return self._registry

    @property
    def owner_ids(self) -> set:
        if self._owner_ids is None:
            from genesis_protocol.agentic.policy import owner_ids_from_env

            self._owner_ids = owner_ids_from_env()
        return self._owner_ids

    # -- principal resolution -------------------------------------------------

    @staticmethod
    def resolve_principal(interface: str, raw: Any) -> Optional[str]:
        """Map an interface-specific identity to a Genesis principal string.

        Telegram and web use numeric user ids; GitHub and Gluten use actor names.
        An unknown interface or an empty identity resolves to None (fail closed).
        """
        if interface not in KNOWN_INTERFACES:
            return None
        if raw is None or str(raw).strip() == "":
            return None
        if interface in ("telegram", "web", "api"):
            try:
                return str(int(raw))
            except (TypeError, ValueError):
                return None
        return str(raw).strip()

    def is_owner(self, interface: str, raw: Any) -> bool:
        principal = self.resolve_principal(interface, raw)
        if principal is None:
            return False
        try:
            return self.policy.is_owner(int(principal))
        except (TypeError, ValueError):
            return False

    # -- authorization --------------------------------------------------------

    def authorize_tool(self, interface: str, raw: Any, tool_name: str,
                       owner_approved: bool = False, agent_id: Optional[str] = None) -> InterfaceDecision:
        """Authorize a tool call consistently across interfaces."""
        if interface not in KNOWN_INTERFACES:
            return InterfaceDecision(False, f"unknown interface '{interface}'", interface)
        principal = self.resolve_principal(interface, raw)
        if principal is None:
            return InterfaceDecision(False, "unresolved principal", interface)

        # An agent caller is authorized through its capability manifest, so the
        # same grant governs it whether it acts via web, Telegram or Gluten.
        if agent_id:
            allowed = self.registry.can_use(agent_id, tool_name, owner_approved=owner_approved)
            return InterfaceDecision(
                allowed, "agent capability manifest" if allowed else "outside agent grant",
                interface, agent_id, requires_owner_approval=not allowed,
            )

        permission = self.registry._permission_of(tool_name)
        try:
            user_id = int(principal)
        except ValueError:
            user_id = None
        decision = self.policy.authorize_tool(user_id, tool_name, permission, owner_approved=owner_approved)
        return InterfaceDecision(decision.allowed, decision.reason, interface, principal,
                                 requires_owner_approval=bool(getattr(decision, "requires_owner_approval", False)))

    def authorize_operation(self, interface: str, raw: Any, operation: str,
                            owner_approved: bool = False) -> InterfaceDecision:
        if interface not in KNOWN_INTERFACES:
            return InterfaceDecision(False, f"unknown interface '{interface}'", interface)
        principal = self.resolve_principal(interface, raw)
        if principal is None:
            return InterfaceDecision(False, "unresolved principal", interface)
        try:
            user_id = int(principal)
        except ValueError:
            user_id = None
        decision = self.policy.authorize_operation(user_id, operation, owner_approved=owner_approved)
        return InterfaceDecision(decision.allowed, decision.reason, interface, principal,
                                 requires_owner_approval=bool(getattr(decision, "requires_owner_approval", False)))

    def status(self) -> Dict[str, Any]:
        return {"interfaces": sorted(KNOWN_INTERFACES), "owners_configured": len(self.owner_ids)}
