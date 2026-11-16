"""Secure agent coordination (V7 P7).

Coordinates multiple Genesis agents without giving any of them new authority.

* ``registry``    - derives capability manifests from the canonical
                    ``IdentityRegistry``; never widens a grant.
* ``messaging``   - signed, replay-protected agent-to-agent envelopes.
* ``tasks``       - single-owner task assignment, deduplication, delegation and
                    conflict resolution (child grants must be a subset).
* ``context``     - shared task context, filtered by clearance and with secrets
                    redacted before sharing.
* ``interfaces``  - one authorizer so Telegram, GitHub, web and Gluten resolve to
                    the same canonical policy.
* ``manager``     - a facade that wires the above together for callers.

Rule: no agent may grant itself or another agent additional privileges. Every
capability is derived from the identity registry and can only narrow.
"""
from genesis_protocol.coordination.context import ContextEntry, SharedContext
from genesis_protocol.coordination.interfaces import InterfaceAuthorizer, InterfaceDecision
from genesis_protocol.coordination.manager import CoordinationManager, get_coordination_manager
from genesis_protocol.coordination.messaging import Envelope, MessageBus, MessageError
from genesis_protocol.coordination.registry import CapabilityManifest, CapabilityRegistry, ProviderRecord
from genesis_protocol.coordination.tasks import CoordinationError, OwnedTask, TaskCoordinator

__all__ = [
    "CapabilityRegistry",
    "CapabilityManifest",
    "ProviderRecord",
    "MessageBus",
    "Envelope",
    "MessageError",
    "TaskCoordinator",
    "OwnedTask",
    "CoordinationError",
    "SharedContext",
    "ContextEntry",
    "InterfaceAuthorizer",
    "InterfaceDecision",
    "CoordinationManager",
    "get_coordination_manager",
]
