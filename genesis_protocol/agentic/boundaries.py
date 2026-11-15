"""Permission boundaries: the least-privilege gate for agent tool calls.

This module is deliberately thin. It does not re-implement permissions; it
composes the two canonical engines that already exist:

* ``genesis_protocol.agentic.policy.AgentPolicy`` - the fail-closed owner/tool
  policy (safe / restricted / admin).
* ``genesis_protocol.tools.tool_registry.ToolRegistry`` - the single source of
  truth for a tool's permission level.

On top of them it adds one thing: an agent's *identity grant* acts as a ceiling.
A tool may run only when the canonical policy allows it **and** the tool is
within the agent's grant. The grant can only narrow, never widen, what policy
allows, so identity can never become a way to escalate privilege.

Precedence, fail closed at every step:

1. The agent identity must verify (exists, active, credential valid).
2. The tool must exist in the registry and be enabled.
3. The canonical ``AgentPolicy`` must allow the call.
4. The tool must be within the agent's grant (when the agent carries a grant).

Any missing piece denies the call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from genesis_protocol.agentic.identity_registry import (
    IdentityRegistry,
    get_identity_registry,
)
from genesis_protocol.agentic.policy import AgentPolicy, get_agent_policy


@dataclass(frozen=True)
class BoundaryDecision:
    """The combined identity + policy decision for a tool call."""

    allowed: bool
    reason: str
    requires_owner_approval: bool = False
    agent_id: Optional[str] = None
    tool: Optional[str] = None
    permission: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_owner_approval": self.requires_owner_approval,
            "agent_id": self.agent_id,
            "tool": self.tool,
            "permission": self.permission,
        }


class BoundaryGuard:
    """Enforces an agent's least-privilege boundary around the canonical policy."""

    def __init__(
        self,
        identities: Optional[IdentityRegistry] = None,
        policy: Optional[AgentPolicy] = None,
        tool_registry: Optional[Any] = None,
    ):
        self.identities = identities or get_identity_registry()
        self.policy = policy or get_agent_policy()
        self._tool_registry = tool_registry

    @property
    def tool_registry(self) -> Any:
        if self._tool_registry is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._tool_registry = get_tool_registry()
        return self._tool_registry

    def check_tool(
        self,
        agent_id: Optional[str],
        tool_name: str,
        user_id: Optional[int] = None,
        credential: Optional[str] = None,
        owner_approved: bool = False,
    ) -> BoundaryDecision:
        """Decide whether ``agent_id`` may call ``tool_name``.

        Every gate is fail-closed: an unverifiable identity, an unknown or
        disabled tool, a policy denial, or a tool outside the agent's grant all
        produce ``allowed=False``.
        """
        verification = self.identities.verify(agent_id, credential=credential)
        if not verification.ok:
            return BoundaryDecision(
                False, f"identity not verified: {verification.reason}", agent_id=agent_id, tool=tool_name
            )

        tool = self.tool_registry.get_tool(tool_name)
        if tool is None:
            return BoundaryDecision(
                False, f"tool '{tool_name}' is not available", agent_id=agent_id, tool=tool_name
            )

        permission = getattr(getattr(tool, "permission", None), "value", None)
        identity = self.identities.get(agent_id)
        if identity is not None and identity.tools and tool_name not in identity.tools:
            return BoundaryDecision(
                False,
                f"tool '{tool_name}' is outside this agent's grant",
                agent_id=agent_id,
                tool=tool_name,
                permission=permission,
            )

        decision = self.policy.authorize_tool(
            user_id, tool_name, permission=permission, owner_approved=owner_approved
        )
        return BoundaryDecision(
            allowed=decision.allowed,
            reason=decision.reason,
            requires_owner_approval=decision.requires_owner_approval,
            agent_id=agent_id,
            tool=tool_name,
            permission=permission,
        )

    def check_operation(
        self, agent_id: Optional[str], operation: str, user_id: Optional[int] = None
    ) -> BoundaryDecision:
        """Decide whether ``agent_id`` may perform a named operation.

        Privileged operations (deploy, merge, secret change, ...) are always
        denied, whatever the agent's grant or status.
        """
        verification = self.identities.verify(agent_id)
        if not verification.ok:
            return BoundaryDecision(
                False, f"identity not verified: {verification.reason}", agent_id=agent_id
            )
        decision = self.policy.authorize_operation(user_id, operation)
        return BoundaryDecision(
            allowed=decision.allowed,
            reason=decision.reason,
            requires_owner_approval=decision.requires_owner_approval,
            agent_id=agent_id,
        )
