"""Verifiable agent identity registry for GLUTEN.

Every agent that may act inside Genesis is registered here first and gets a
unique, immutable identity: who it is, which provider/model it runs on, which
agent it descends from, which human owner it answers to, its role and its
status. Nothing else in the system may invent an agent.

Design rules, in priority order:

1. Fail closed. An unknown, suspended or revoked agent fails verification, and
   a failed verification denies every privileged action.
2. No self-granting. Registering an agent, changing its tool grants, suspending,
   revoking or reactivating it all require ``owner_approved=True``. The registry
   never sets that flag itself, and an agent cannot widen its own identity.
3. Permissions only narrow down the tree. A child agent's tool grant must be a
   subset of its parent's, so a forged or over-privileged child is refused.
4. This registry is an *identity* store, not a second permission engine. Whether
   a tool may run is decided by the canonical ``ToolRegistry`` permission and the
   canonical ``AgentPolicy`` - see ``agentic.boundaries``. The tool grants here
   are a ceiling that can only restrict, never expand, what policy allows.

Nothing here grants autonomy, deploys, touches secrets or writes to main.
"""
from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from genesis_protocol.agentic.audit import AuditLog, get_audit_log
from genesis_protocol.agentic.credentials import CredentialStore, get_credential_store

AGENT_STATUSES = ("active", "suspended", "revoked")

_ID_RE = re.compile(r"^agt_[0-9a-f]{12}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_NAME_MAX = 64


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class IdentityError(ValueError):
    """Raised when an identity operation is not allowed (fail closed)."""


@dataclass
class AgentIdentity:
    """An immutable agent identity record. It holds no secret value."""

    agent_id: str
    name: str
    role: str
    owner_id: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    parent_id: Optional[str] = None
    status: str = "active"
    tools: Tuple[str, ...] = ()
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for reports. Identities carry no credential material."""
        data = asdict(self)
        data["tools"] = list(self.tools)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentIdentity":
        data = dict(data)
        data["tools"] = tuple(data.get("tools", ()))
        return cls(**data)


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying an agent's identity before a privileged action."""

    ok: bool
    reason: str
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "agent_id": self.agent_id}


class IdentityRegistry:
    """Registry of agent identities. Thread-safe, optionally durable."""

    def __init__(
        self,
        path: Optional[str] = None,
        tool_registry: Optional[Any] = None,
        credentials: Optional[CredentialStore] = None,
        audit: Optional[AuditLog] = None,
    ):
        if path is None:
            path = str(Path("data") / "gluten_agents.json")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._agents: Dict[str, AgentIdentity] = {}
        self._tool_registry = tool_registry
        self._credentials = credentials or get_credential_store()
        self.audit = audit or get_audit_log()
        self._load()

    # -- canonical tool registry (lazy so import order stays clean) -----------

    @property
    def tool_registry(self) -> Any:
        if self._tool_registry is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._tool_registry = get_tool_registry()
        return self._tool_registry

    # -- persistence ----------------------------------------------------------

    def _load(self) -> None:
        if self.path == ":memory:" or not Path(self.path).exists():
            return
        try:
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in raw.get("agents", []):
            try:
                identity = AgentIdentity.from_dict(item)
                self._agents[identity.agent_id] = identity
            except (TypeError, KeyError):
                continue

    def _save(self) -> None:
        if self.path == ":memory:":
            return
        payload = {"agents": [a.to_dict() for a in self._agents.values()]}
        tmp = Path(self.path).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic swap so a crash cannot truncate state

    # -- reads ----------------------------------------------------------------

    def get(self, agent_id: Optional[str]) -> Optional[AgentIdentity]:
        if not agent_id:
            return None
        with self._lock:
            return self._agents.get(agent_id)

    def get_by_name(self, name: str) -> Optional[AgentIdentity]:
        with self._lock:
            for identity in self._agents.values():
                if identity.name == name:
                    return identity
        return None

    def list_agents(self) -> List[AgentIdentity]:
        with self._lock:
            return sorted(self._agents.values(), key=lambda a: a.created_at)

    def descendants(self, agent_id: str) -> List[AgentIdentity]:
        """Every agent that descends from ``agent_id`` (transitively)."""
        with self._lock:
            children: Dict[str, List[AgentIdentity]] = {}
            for identity in self._agents.values():
                children.setdefault(identity.parent_id or "", []).append(identity)
            out: List[AgentIdentity] = []
            stack = list(children.get(agent_id, []))
            while stack:
                node = stack.pop()
                out.append(node)
                stack.extend(children.get(node.agent_id, []))
            return out

    # -- registration ---------------------------------------------------------

    def register(
        self,
        name: str,
        role: str,
        owner_id: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        parent_id: Optional[str] = None,
        tools: Iterable[str] = (),
        owner_approved: bool = False,
        agent_id: Optional[str] = None,
    ) -> AgentIdentity:
        """Register a new agent identity.

        Registration is an owner action: ``owner_approved`` must be True. The
        tool grant is validated against the canonical ``ToolRegistry`` (an
        unknown tool is refused) and, when a parent is given, must be a subset
        of the parent's grant so privilege can only narrow down the tree.
        """
        if not owner_approved:
            raise IdentityError("registering an agent requires owner approval")

        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > _NAME_MAX:
            raise IdentityError(f"agent name must be 1-{_NAME_MAX} characters")
        if not _ROLE_RE.fullmatch((role or "").strip()):
            raise IdentityError(f"invalid role '{role}'")
        role = role.strip()
        if owner_id is not None and not isinstance(owner_id, int):
            raise IdentityError("owner_id must be an integer or None")

        provider = self._clean_optional(provider, "provider")
        model = self._clean_optional(model, "model")

        grant = self._validate_tools(tools)

        parent: Optional[AgentIdentity] = None
        if parent_id is not None:
            parent = self.get(parent_id)
            if parent is None:
                raise IdentityError(f"parent agent '{parent_id}' does not exist")
            if parent.status != "active":
                raise IdentityError(f"parent agent '{parent_id}' is not active")
            over = set(grant) - set(parent.tools)
            if over:
                raise IdentityError(
                    "child grant exceeds parent grant: " + ", ".join(sorted(over))
                )

        new_id = agent_id or f"agt_{uuid.uuid4().hex[:12]}"
        if not _ID_RE.fullmatch(new_id):
            raise IdentityError(f"invalid agent_id '{new_id}'")

        with self._lock:
            if new_id in self._agents:
                raise IdentityError(f"agent '{new_id}' already exists")
            if any(a.name == clean_name for a in self._agents.values()):
                raise IdentityError(f"agent name '{clean_name}' already registered")
            identity = AgentIdentity(
                agent_id=new_id,
                name=clean_name,
                role=role,
                owner_id=owner_id,
                provider=provider,
                model=model,
                parent_id=parent_id,
                status="active",
                tools=tuple(grant),
            )
            self._agents[new_id] = identity
            self._save()

        self.audit.record(
            "agent_registered",
            user_id=owner_id,
            agent_id=new_id,
            allowed=True,
            reason=f"role={role} parent={parent_id or '-'} tools={len(grant)}",
        )
        return identity

    def _clean_optional(self, value: Optional[str], field_name: str) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        if len(value) > _NAME_MAX:
            raise IdentityError(f"{field_name} must be <= {_NAME_MAX} characters")
        return value

    def _validate_tools(self, tools: Iterable[str]) -> Tuple[str, ...]:
        out: List[str] = []
        for raw in tools or ():
            name = str(raw).strip()
            if not name:
                continue
            if self.tool_registry.get_tool(name) is None:
                raise IdentityError(f"unknown tool '{name}' (not in the tool registry)")
            if name not in out:
                out.append(name)
        return tuple(out)

    # -- grant management (owner action, can only narrow or extend explicitly) -

    def update_grants(
        self,
        agent_id: str,
        add: Iterable[str] = (),
        remove: Iterable[str] = (),
        owner_approved: bool = False,
    ) -> AgentIdentity:
        """Change an agent's tool ceiling. Requires owner approval.

        New tools are validated against the canonical registry, and a child's
        resulting grant may not exceed its parent's. A grant is a ceiling: it
        never widens what the canonical policy allows.
        """
        if not owner_approved:
            raise IdentityError("changing tool grants requires owner approval")
        identity = self.get(agent_id)
        if identity is None:
            raise IdentityError(f"unknown agent '{agent_id}'")

        grant = set(identity.tools)
        grant.update(self._validate_tools(add))
        for raw in remove or ():
            grant.discard(str(raw).strip())

        if identity.parent_id:
            parent = self.get(identity.parent_id)
            if parent is not None:
                over = grant - set(parent.tools)
                if over:
                    raise IdentityError(
                        "grant would exceed parent grant: " + ", ".join(sorted(over))
                    )

        with self._lock:
            identity.tools = tuple(sorted(grant))
            identity.updated_at = _utcnow()
            self._save()
        self.audit.record(
            "agent_grant_updated",
            user_id=identity.owner_id,
            agent_id=agent_id,
            allowed=True,
            reason=f"tools={len(identity.tools)}",
        )
        return identity

    # -- status changes (owner action) ----------------------------------------

    def suspend(self, agent_id: str, reason: str = "", owner_approved: bool = False) -> AgentIdentity:
        """Suspend an agent and its descendants. Requires owner approval."""
        return self._set_status(agent_id, "suspended", reason, owner_approved, cascade=True)

    def reactivate(self, agent_id: str, owner_approved: bool = False) -> AgentIdentity:
        """Reactivate a suspended agent. Refuses if an ancestor is revoked."""
        if not owner_approved:
            raise IdentityError("reactivating an agent requires owner approval")
        identity = self.get(agent_id)
        if identity is None:
            raise IdentityError(f"unknown agent '{agent_id}'")
        if identity.status == "revoked":
            raise IdentityError("a revoked agent cannot be reactivated")
        ancestor = self._revoked_ancestor(identity)
        if ancestor is not None:
            raise IdentityError(f"ancestor '{ancestor}' is revoked")
        with self._lock:
            identity.status = "active"
            identity.updated_at = _utcnow()
            self._save()
        self.audit.record("agent_reactivated", user_id=identity.owner_id, agent_id=agent_id,
                          allowed=True, reason="")
        return identity

    def revoke(self, agent_id: str, reason: str = "", owner_approved: bool = False) -> List[AgentIdentity]:
        """Revoke an agent and every descendant. Requires owner approval.

        Revocation is permanent and also drops any live credentials for the
        affected agents, so a compromised identity cannot keep acting. Returns
        every identity that was revoked.
        """
        if not owner_approved:
            raise IdentityError("revoking an agent requires owner approval")
        identity = self.get(agent_id)
        if identity is None:
            raise IdentityError(f"unknown agent '{agent_id}'")

        affected = [identity] + self.descendants(agent_id)
        with self._lock:
            for item in affected:
                item.status = "revoked"
                item.updated_at = _utcnow()
            self._save()
        for item in affected:
            self._credentials.revoke_for_agent(item.agent_id)
            self.audit.record("agent_revoked", user_id=identity.owner_id, agent_id=item.agent_id,
                              allowed=False, reason=reason or "revoked")
        return affected

    def _set_status(
        self, agent_id: str, status: str, reason: str, owner_approved: bool, cascade: bool
    ) -> AgentIdentity:
        if not owner_approved:
            raise IdentityError(f"{status} requires owner approval")
        if status not in AGENT_STATUSES:
            raise IdentityError(f"invalid status '{status}'")
        identity = self.get(agent_id)
        if identity is None:
            raise IdentityError(f"unknown agent '{agent_id}'")
        targets = [identity] + (self.descendants(agent_id) if cascade else [])
        with self._lock:
            for item in targets:
                if item.status != "revoked":  # never resurrect a revoked agent
                    item.status = status
                    item.updated_at = _utcnow()
            self._save()
        for item in targets:
            if status != "active":
                self._credentials.revoke_for_agent(item.agent_id)
            self.audit.record(f"agent_{status}", user_id=identity.owner_id, agent_id=item.agent_id,
                              allowed=(status == "active"), reason=reason or status)
        return identity

    def _revoked_ancestor(self, identity: AgentIdentity) -> Optional[str]:
        seen = set()
        current = identity.parent_id
        while current and current not in seen:
            seen.add(current)
            ancestor = self.get(current)
            if ancestor is None:
                return None
            if ancestor.status == "revoked":
                return ancestor.agent_id
            current = ancestor.parent_id
        return None

    # -- verification ---------------------------------------------------------

    def verify(self, agent_id: Optional[str], credential: Optional[str] = None) -> VerificationResult:
        """Verify an agent before a privileged action.

        Checks that the identity exists and is active, and - when a credential
        is supplied - that the credential is live and belongs to this agent.
        Any failure denies the action (fail closed).
        """
        if not agent_id:
            return VerificationResult(False, "no agent identity supplied")
        identity = self.get(agent_id)
        if identity is None:
            return VerificationResult(False, f"unknown agent '{agent_id}'")
        if identity.status == "revoked":
            return VerificationResult(False, f"agent '{agent_id}' is revoked", agent_id)
        if identity.status != "active":
            return VerificationResult(False, f"agent '{agent_id}' is {identity.status}", agent_id)
        if credential is not None:
            check = self._credentials.verify(credential)
            if not check.ok:
                return VerificationResult(False, f"credential rejected: {check.reason}", agent_id)
            if check.agent_id != agent_id:
                return VerificationResult(
                    False, "credential does not belong to this agent", agent_id
                )
        return VerificationResult(True, "identity verified", agent_id)


_default: Optional[IdentityRegistry] = None


def get_identity_registry() -> IdentityRegistry:
    """Process-wide identity registry (durable unless GLUTEN_AGENT_DB overrides)."""
    global _default
    if _default is None:
        import os

        _default = IdentityRegistry(os.environ.get("GLUTEN_AGENT_DB"))
    return _default
