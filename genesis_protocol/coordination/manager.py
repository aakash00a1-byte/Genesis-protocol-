"""Coordination facade (V7 P7).

Wires the coordination components together and offers the few operations the rest
of Genesis needs, so callers do not have to assemble them:

* ``manifest`` / ``manifests`` - capability views over the identity registry.
* ``authorize`` - one authorization call for every interface.
* ``assign`` / ``delegate`` / ``complete`` - task ownership with deduplication.
* ``send`` / ``receive`` - signed agent messages.
* ``share_context`` / ``view_context`` - privacy-filtered context.
* ``status`` - a compact, secret-free summary.

It grants no capability: every operation delegates to the canonical systems.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from genesis_protocol.coordination.context import SharedContext
from genesis_protocol.coordination.interfaces import InterfaceAuthorizer
from genesis_protocol.coordination.messaging import Envelope, MessageBus
from genesis_protocol.coordination.registry import CapabilityRegistry
from genesis_protocol.coordination.tasks import TaskCoordinator


class CoordinationManager:
    """A single entry point for secure multi-agent coordination."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None,
                 bus: Optional[MessageBus] = None,
                 coordinator: Optional[TaskCoordinator] = None,
                 context: Optional[SharedContext] = None,
                 authorizer: Optional[InterfaceAuthorizer] = None):
        self.registry = registry or CapabilityRegistry()
        self.bus = bus or MessageBus()
        self.tasks = coordinator or TaskCoordinator(registry=self.registry)
        self.context = context or SharedContext()
        self.authorizer = authorizer or InterfaceAuthorizer()

    # -- capabilities ---------------------------------------------------------

    def manifest(self, agent_id: str) -> Optional[Dict[str, Any]]:
        m = self.registry.manifest(agent_id)
        return m.to_dict() if m else None

    def manifests(self) -> List[Dict[str, Any]]:
        return [m.to_dict() for m in self.registry.manifests()]

    def authorize(self, interface: str, raw: Any, tool_name: str,
                  agent_id: Optional[str] = None, owner_approved: bool = False) -> Dict[str, Any]:
        return self.authorizer.authorize_tool(interface, raw, tool_name,
                                              agent_id=agent_id, owner_approved=owner_approved).to_dict()

    # -- tasks ----------------------------------------------------------------

    def assign(self, owner: str, idempotency_key: str = "") -> Dict[str, Any]:
        return self.tasks.assign(owner, idempotency_key).to_dict()

    def delegate(self, task_id: str, from_agent: str, to_agent: str) -> Dict[str, Any]:
        return self.tasks.delegate(task_id, from_agent, to_agent).to_dict()

    def complete(self, task_id: str, actor: str) -> Dict[str, Any]:
        return self.tasks.update_state(task_id, actor, "completed").to_dict()

    # -- messaging ------------------------------------------------------------

    def send(self, sender: str, recipient: str, message_type: str, payload: Dict[str, Any],
             credential: str, nonce: str = "", sent_at: str = "") -> Dict[str, Any]:
        import secrets
        from datetime import datetime, timezone

        envelope = Envelope(
            sender=sender, recipient=recipient, message_type=message_type, payload=payload,
            nonce=nonce or secrets.token_hex(16),
            sent_at=sent_at or datetime.now(timezone.utc).isoformat(),
        )
        return self.bus.send(envelope, credential).to_dict()

    def receive(self, envelope: Dict[str, Any], credential: str) -> Dict[str, Any]:
        env = Envelope(**{k: envelope[k] for k in
                          ("sender", "recipient", "message_type", "payload", "nonce", "sent_at",
                           "signature") if k in envelope})
        return self.bus.receive(env, credential).to_dict()

    # -- context --------------------------------------------------------------

    def share_context(self, task_id: str, key: str, value: str, originator: str,
                      sensitivity: str = "internal") -> Dict[str, Any]:
        return self.context.put(task_id, key, value, originator, sensitivity).to_dict()

    def view_context(self, task_id: str, role: str, requester: str,
                     owner: Optional[str] = None) -> Dict[str, Any]:
        return self.context.view(task_id, role, requester, owner=owner)

    # -- status ---------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "agents": len(self.manifests()),
            "messages": self.bus.status(),
            "tasks": self.tasks.status(),
            "context": self.context.status(),
            "interfaces": self.authorizer.status(),
            "providers": self.registry.provider_status(),
        }


_default: Optional[CoordinationManager] = None


def get_coordination_manager() -> CoordinationManager:
    global _default
    if _default is None:
        _default = CoordinationManager()
    return _default
