"""Authenticated agent-to-agent messaging (V7 P7).

Agents exchange **envelopes**. An envelope is signed with the sender's
short-lived credential and validated by the receiver before it is read:

* **Authenticity** - the sender identity must exist, be active and present a live
  credential that belongs to it (via the canonical ``IdentityRegistry.verify``).
* **Integrity** - the payload is signed with an HMAC keyed by the credential, so
  a tampered body is rejected.
* **Freshness** - every envelope carries a timestamp and a nonce; a nonce seen
  before is rejected (replay protection) and an envelope outside the freshness
  window is rejected.
* **Provenance** - the receiver records who sent what and when, so a task can be
  traced back to its originator.

Messages are also *validated for shape*: an unknown message type or a payload
missing a required field is rejected. External/retrieved content is never
trusted: only a verified identity can put a message on the bus.

The bus holds no long-term secret. The signing key is the credential token the
sender was issued; it is never stored by the bus, only used to verify a digest.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Set

DEFAULT_FRESHNESS_SECONDS = 120
DEFAULT_MAX_MESSAGES = 2000

# Allowed message types. An unknown type is rejected rather than forwarded.
MESSAGE_TYPES = frozenset({
    "task.assign",
    "task.accept",
    "task.result",
    "task.status",
    "task.cancel",
    "context.share",
    "handoff",
    "heartbeat",
})

# Required payload fields per message type.
REQUIRED_FIELDS: Dict[str, tuple] = {
    "task.assign": ("task_id",),
    "task.accept": ("task_id",),
    "task.result": ("task_id", "status"),
    "task.status": ("task_id", "state"),
    "task.cancel": ("task_id",),
    "context.share": ("task_id", "context"),
    "handoff": ("task_id", "to"),
    "heartbeat": (),
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


@dataclass
class Envelope:
    """A signed, validated agent-to-agent message."""

    sender: str
    recipient: str
    message_type: str
    payload: Dict[str, Any]
    nonce: str
    sent_at: str
    signature: str = ""
    validated: bool = False
    received_at: Optional[str] = None

    def signing_body(self) -> str:
        return _canonical({
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "payload": self.payload,
            "nonce": self.nonce,
            "sent_at": self.sent_at,
        })

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MessageError(ValueError):
    """Raised when an envelope fails validation."""


class MessageBus:
    """A signed message bus with replay and shape protection."""

    def __init__(self, identities: Optional[Any] = None,
                 credentials: Optional[Any] = None,
                 freshness_seconds: int = DEFAULT_FRESHNESS_SECONDS,
                 max_messages: int = DEFAULT_MAX_MESSAGES):
        self._identities = identities
        self._credentials = credentials
        self.freshness_seconds = freshness_seconds
        self.max_messages = max_messages
        self._lock = threading.Lock()
        self._messages: Deque[Envelope] = deque(maxlen=max_messages)
        self._seen_nonces: Set[str] = set()
        self._nonce_order: Deque[str] = deque(maxlen=max_messages)

    @property
    def identities(self) -> Any:
        if self._identities is None:
            from genesis_protocol.agentic.identity_registry import get_identity_registry

            self._identities = get_identity_registry()
        return self._identities

    @property
    def credentials(self) -> Any:
        if self._credentials is None:
            from genesis_protocol.agentic.credentials import get_credential_store

            self._credentials = get_credential_store()
        return self._credentials

    def _authenticate(self, agent_id: Optional[str], credential: Optional[str]) -> None:
        """Verify sender identity + credential without consuming a use.

        A message credential is a TTL-bounded *signing key*, not a one-time
        action token, so verifying it must not spend one of its uses. The
        canonical ``CredentialStore.verify`` is reused with ``consume=False``.
        Any failure raises (fail closed).
        """
        if not agent_id:
            raise MessageError("sender identity is required")
        identity = self.identities.get(agent_id)
        if identity is None:
            raise MessageError(f"unknown sender '{agent_id}'")
        if identity.status != "active":
            raise MessageError(f"sender '{agent_id}' is {identity.status}")
        check = self.credentials.verify(credential, consume=False)
        if not check.ok:
            raise MessageError(f"sender not authenticated: {check.reason}")
        if check.agent_id != agent_id:
            raise MessageError("credential does not belong to the sender")

    # -- signing --------------------------------------------------------------

    @staticmethod
    def sign(envelope: Envelope, credential: str) -> str:
        """Compute the HMAC signature for an envelope with the sender's credential."""
        return hmac.new(credential.encode("utf-8"), envelope.signing_body().encode("utf-8"),
                        hashlib.sha256).hexdigest()

    @staticmethod
    def validate_shape(message_type: str, payload: Dict[str, Any]) -> None:
        if message_type not in MESSAGE_TYPES:
            raise MessageError(f"unknown message type '{message_type}'")
        for field_name in REQUIRED_FIELDS.get(message_type, ()):
            if field_name not in (payload or {}):
                raise MessageError(f"message '{message_type}' is missing required field '{field_name}'")

    # -- send / receive -------------------------------------------------------

    def send(self, envelope: Envelope, credential: str) -> Envelope:
        """Sign and enqueue an envelope. The credential is verified first."""
        self._authenticate(envelope.sender, credential)
        self.validate_shape(envelope.message_type, envelope.payload)
        envelope.signature = self.sign(envelope, credential)
        envelope.validated = True
        envelope.received_at = _utcnow()
        with self._lock:
            self._messages.append(envelope)
        return envelope

    def receive(self, envelope: Envelope, credential: str) -> Envelope:
        """Validate a received envelope before it may be read.

        Checks shape, sender authentication, signature, freshness and replay.
        Any failure raises and the message is not delivered.
        """
        self.validate_shape(envelope.message_type, envelope.payload)
        self._authenticate(envelope.sender, credential)
        expected = self.sign(envelope, credential)
        if not hmac.compare_digest(expected, envelope.signature or ""):
            raise MessageError("signature mismatch: message was altered")
        try:
            sent = datetime.fromisoformat(envelope.sent_at.replace("Z", "+00:00")).timestamp()
        except Exception as exc:
            raise MessageError(f"unparseable timestamp: {exc}") from exc
        age = abs(time.time() - sent)
        if age > self.freshness_seconds:
            raise MessageError(f"message is stale ({age:.0f}s old)")
        with self._lock:
            if envelope.nonce in self._seen_nonces:
                raise MessageError("replay detected: nonce already seen")
            self._seen_nonces.add(envelope.nonce)
            self._nonce_order.append(envelope.nonce)
            while len(self._seen_nonces) > self.max_messages and self._nonce_order:
                self._seen_nonces.discard(self._nonce_order.popleft())
        envelope.validated = True
        envelope.received_at = _utcnow()
        return envelope

    # -- read side ------------------------------------------------------------

    def messages(self, recipient: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._messages)
        out = []
        for m in items:
            if recipient and m.recipient != recipient:
                continue
            if task_id and m.payload.get("task_id") != task_id:
                continue
            out.append(m.to_dict())
        return out

    def provenance(self, task_id: str) -> List[Dict[str, Any]]:
        """The ordered chain of messages for one task (who did what, when)."""
        chain = self.messages(task_id=task_id)
        chain.sort(key=lambda m: m.get("sent_at") or "")
        return chain

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {"messages": len(self._messages), "seen_nonces": len(self._seen_nonces),
                    "freshness_seconds": self.freshness_seconds}
