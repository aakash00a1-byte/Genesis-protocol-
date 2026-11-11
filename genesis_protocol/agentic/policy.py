"""Fail-closed authorization policy for GLUTEN's tool and task execution.

Design rules, in priority order:

1. Fail closed. Anything unknown - unknown tool, unknown permission, missing
   owner configuration - is denied.
2. No self-granting. The agent cannot widen its own permissions; grants come
   from configuration, not from the model.
3. No self-approval. ``owner_approved`` is supplied by the caller (a human or
   owner-scoped surface), never by the agent loop. This module never sets it.
4. Privileged operations - deploy, secret changes, writes to main, merges,
   self-approval, permission grants, settings changes - are never allowed to
   the agent, whatever the caller claims. They require owner action outside the
   agent.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Optional, Set

# Operations the agent must never perform for itself. Listed explicitly so a
# new caller cannot accidentally route one through ``authorize_operation``.
PRIVILEGED_OPERATIONS = frozenset(
    {
        "deploy",
        "modify_secret",
        "change_secret",
        "write_main",
        "push_main",
        "merge_pr",
        "self_approve",
        "grant_permission",
        "change_settings",
        "delete_repo",
    }
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_owner_approval: bool = False

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "requires_owner_approval": self.requires_owner_approval,
        }


def _owner_ids_from_env() -> Set[int]:
    raw = os.environ.get("GLUTEN_OWNER_IDS", "").strip()
    ids: Set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.add(int(chunk))
    return ids


class AgentPolicy:
    """Decides whether a user may invoke a tool or operation."""

    def __init__(self, owner_ids: Optional[Iterable[int]] = None):
        if owner_ids is None:
            owner_ids = _owner_ids_from_env()
        self.owner_ids: Set[int] = {int(i) for i in owner_ids}

    def is_owner(self, user_id: Optional[int]) -> bool:
        return user_id is not None and int(user_id) in self.owner_ids

    def authorize_operation(
        self,
        user_id: Optional[int],
        operation: str,
        owner_approved: bool = False,
    ) -> PolicyDecision:
        """Authorize a named operation. Privileged ops are always denied."""
        op = (operation or "").strip().lower()
        if not op:
            return PolicyDecision(False, "empty operation")
        if op in PRIVILEGED_OPERATIONS:
            # Deliberately ignores owner_approved: the agent must not be able to
            # approve its own privileged action, and these are out of scope for
            # the agent entirely.
            return PolicyDecision(
                False,
                f"'{op}' is a privileged operation; it requires owner action outside the agent",
                requires_owner_approval=True,
            )
        return PolicyDecision(True, f"operation '{op}' is not privileged")

    def authorize_tool(
        self,
        user_id: Optional[int],
        tool_name: str,
        permission: Optional[str] = None,
        owner_approved: bool = False,
    ) -> PolicyDecision:
        """Authorize a tool call from its registry permission level."""
        if not tool_name:
            return PolicyDecision(False, "unknown tool")

        # Unknown permission -> deny (fail closed).
        perm = (permission or "").strip().lower()
        if perm not in {"safe", "restricted", "admin"}:
            return PolicyDecision(False, f"unknown permission level for tool '{tool_name}'")

        if perm == "safe":
            return PolicyDecision(True, "safe tool")

        if not self.owner_ids:
            return PolicyDecision(
                False,
                f"tool '{tool_name}' is {perm}; no owner is configured",
                requires_owner_approval=True,
            )

        if not self.is_owner(user_id):
            return PolicyDecision(
                False,
                f"tool '{tool_name}' is {perm}; user {user_id} is not the owner",
                requires_owner_approval=True,
            )

        if perm == "admin":
            return PolicyDecision(True, "owner invoking admin tool")

        # restricted: owner must approve explicitly, per call.
        if owner_approved:
            return PolicyDecision(True, "owner-approved restricted tool")
        return PolicyDecision(
            False,
            f"tool '{tool_name}' is restricted; owner approval required",
            requires_owner_approval=True,
        )


_default: Optional[AgentPolicy] = None


def get_agent_policy() -> AgentPolicy:
    global _default
    if _default is None:
        _default = AgentPolicy()
    return _default
