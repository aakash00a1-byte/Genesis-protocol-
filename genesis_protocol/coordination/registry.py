"""Central agent identity and capability registry (V7 P7).

A thin **read-mostly** view over the canonical systems that already own the data:

* ``agentic.identity_registry.IdentityRegistry`` - identities, grants, lineage,
  suspension/revocation.
* ``agentic.policy.AgentPolicy`` - who may use which tool permission.
* ``tools.tool_registry.ToolRegistry`` - the set of tools that exist.

The registry does **not** store grants of its own and offers no method that
widens one. A capability manifest is *derived* from the identity's grant and is
always intersected with the canonical tool set, so a manifest can only ever be
equal to or narrower than what the identity registry already permits. That
property is what makes "no agent may grant itself or another agent additional
privileges" hold by construction rather than by convention.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CapabilityManifest:
    """What one agent is permitted to do, derived from its identity."""

    agent_id: str
    name: str
    role: str
    status: str
    tools: List[str] = field(default_factory=list)
    parent_id: Optional[str] = None
    depth: int = 0
    can_delegate: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    derived_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderRecord:
    """One observed provider/model use by an agent."""

    agent_id: str
    provider: str
    model: str
    ok: bool
    fallback: bool = False
    latency_ms: Optional[float] = None
    at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CapabilityRegistry:
    """Derives capability manifests and tracks provider/model use per agent."""

    # An agent may only delegate when its role is explicitly allowed to.
    DELEGATING_ROLES = frozenset({"coordinator", "operator", "manager"})

    def __init__(self, identities: Optional[Any] = None, policy: Optional[Any] = None,
                 tools: Optional[Any] = None):
        self._identities = identities
        self._policy = policy
        self._tools = tools
        self._providers: List[ProviderRecord] = []
        self._last_provider: Dict[str, str] = {}

    # -- canonical sources ----------------------------------------------------

    @property
    def identities(self) -> Any:
        if self._identities is None:
            from genesis_protocol.agentic.identity_registry import get_identity_registry

            self._identities = get_identity_registry()
        return self._identities

    @property
    def policy(self) -> Any:
        if self._policy is None:
            from genesis_protocol.agentic.policy import get_agent_policy

            self._policy = get_agent_policy()
        return self._policy

    @property
    def tools(self) -> Any:
        if self._tools is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._tools = get_tool_registry()
        return self._tools

    def known_tools(self) -> set:
        try:
            return {t.name for t in self.tools.get_all_tools()}
        except Exception:
            return set()

    # -- manifests ------------------------------------------------------------

    def manifest(self, agent_id: str) -> Optional[CapabilityManifest]:
        identity = self.identities.get(agent_id)
        if identity is None:
            return None
        # Intersect the identity's grant with the canonical tool set: a manifest
        # can never name a tool that does not exist, and never adds one.
        known = self.known_tools()
        granted = [t for t in (identity.tools or []) if not known or t in known]
        parent_id = getattr(identity, "parent_id", None)
        depth = 0
        seen = set()
        cursor = parent_id
        while cursor and cursor not in seen:
            seen.add(cursor)
            depth += 1
            parent = self.identities.get(cursor)
            cursor = getattr(parent, "parent_id", None) if parent else None
        return CapabilityManifest(
            agent_id=identity.agent_id,
            name=identity.name,
            role=identity.role,
            status=identity.status,
            tools=sorted(granted),
            parent_id=parent_id,
            depth=depth,
            can_delegate=identity.role in self.DELEGATING_ROLES and identity.status == "active",
            provider=getattr(identity, "provider", None),
            model=getattr(identity, "model", None),
        )

    def manifests(self) -> List[CapabilityManifest]:
        out = []
        for identity in self.identities.list_agents():
            m = self.manifest(identity.agent_id)
            if m is not None:
                out.append(m)
        return out

    def can_use(self, agent_id: str, tool_name: str, owner_approved: bool = False) -> bool:
        """Whether an agent may use a tool: within its grant AND policy-allowed."""
        identity = self.identities.get(agent_id)
        if identity is None or identity.status != "active":
            return False
        if tool_name not in (identity.tools or []):
            return False
        permission = self._permission_of(tool_name)
        decision = self.policy.authorize_tool(None, tool_name, permission, owner_approved=owner_approved)
        return bool(decision.allowed)

    def _permission_of(self, tool_name: str) -> Optional[str]:
        try:
            for tool in self.tools.get_all_tools():
                if tool.name == tool_name:
                    perm = tool.permission
                    return getattr(perm, "value", perm)
        except Exception:
            return None
        return None

    @staticmethod
    def is_subset(child_tools: List[str], parent_tools: List[str]) -> bool:
        """Whether a child's grant is contained in its parent's (least privilege)."""
        return set(child_tools or []).issubset(set(parent_tools or []))

    # -- provider / model tracking -------------------------------------------

    def record_provider(self, agent_id: str, provider: str, model: str = "",
                        ok: bool = True, latency_ms: Optional[float] = None) -> ProviderRecord:
        previous = self._last_provider.get(agent_id)
        fallback = bool(previous and provider != previous)
        record = ProviderRecord(agent_id=agent_id, provider=provider, model=model,
                                ok=ok, fallback=fallback, latency_ms=latency_ms)
        self._providers.append(record)
        self._last_provider[agent_id] = provider
        # Bounded history.
        if len(self._providers) > 1000:
            self._providers = self._providers[-1000:]
        return record

    def provider_status(self) -> Dict[str, Any]:
        by_agent: Dict[str, Dict[str, Any]] = {}
        fallbacks = 0
        failures = 0
        for record in self._providers:
            entry = by_agent.setdefault(record.agent_id, {"last": None, "uses": 0, "failures": 0, "fallbacks": 0})
            entry["last"] = {"provider": record.provider, "model": record.model, "ok": record.ok}
            entry["uses"] += 1
            if not record.ok:
                entry["failures"] += 1
                failures += 1
            if record.fallback:
                entry["fallbacks"] += 1
                fallbacks += 1
        return {"agents": by_agent, "total_fallbacks": fallbacks, "total_failures": failures}
