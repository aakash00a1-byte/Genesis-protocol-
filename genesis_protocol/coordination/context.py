"""Shared task context with privacy filtering (V7 P7).

Agents working one task need the same context, but not every agent may see every
field. Context is shared as *field-tagged* entries:

* each entry carries a ``sensitivity`` in ``public`` / ``internal`` / ``private``;
* an agent receives only the entries at or below its clearance;
* ``private`` entries are additionally redacted to a marker unless the requester
  is the task owner or the entry's originator.

Secrets are never shared: any value matching a secret shape is replaced with a
marker before it can enter the shared context, so a leaked key cannot propagate
between agents through coordination. This reuses the same redaction used by the
guardian's security log.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SENSITIVITY_RANK = {"public": 0, "internal": 1, "private": 2}

# Clearance per role. A role not listed gets the lowest clearance (fail closed).
ROLE_CLEARANCE: Dict[str, str] = {
    "manager": "private",
    "coordinator": "private",
    "operator": "internal",
    "analyst": "internal",
    "worker": "internal",
    "viewer": "public",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact_secrets(text: str) -> str:
    """Replace any secret-shaped substring with a marker.

    Reuses the guardian's secret patterns so coordination and security agree on
    what a secret looks like. A value with no secret shape is returned unchanged.
    """
    from genesis_protocol.guardian.detection import _SECRET_PATTERNS

    return _SECRET_PATTERNS.sub("<redacted>", text or "")


@dataclass
class ContextEntry:
    key: str
    value: str
    sensitivity: str
    originator: str
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SharedContext:
    """A per-task context store that filters by clearance and redacts secrets."""

    def __init__(self, clearance_map: Optional[Dict[str, str]] = None):
        self._entries: Dict[str, Dict[str, ContextEntry]] = {}
        self._clearance = dict(clearance_map or ROLE_CLEARANCE)

    @classmethod
    def clearance_for(cls, role: str, clearance_map: Optional[Dict[str, str]] = None) -> str:
        mapping = clearance_map or ROLE_CLEARANCE
        return mapping.get((role or "").lower(), "public")

    def put(self, task_id: str, key: str, value: str, originator: str,
            sensitivity: str = "internal") -> ContextEntry:
        if sensitivity not in SENSITIVITY_RANK:
            sensitivity = "private"  # unknown sensitivity is treated as the most restricted
        entry = ContextEntry(key=key, value=redact_secrets(str(value)),
                             sensitivity=sensitivity, originator=originator)
        self._entries.setdefault(task_id, {})[key] = entry
        return entry

    def view(self, task_id: str, role: str, requester: str,
             owner: Optional[str] = None) -> Dict[str, Any]:
        """The context visible to one requester, filtered and redacted."""
        clearance = self.clearance_for(role)
        max_rank = SENSITIVITY_RANK.get(clearance, 0)
        out: Dict[str, Any] = {}
        redacted: List[str] = []
        for key, entry in self._entries.get(task_id, {}).items():
            entry_rank = SENSITIVITY_RANK.get(entry.sensitivity, 2)
            if entry_rank > max_rank:
                redacted.append(key)
                continue
            if entry.sensitivity == "private" and requester != owner and requester != entry.originator:
                redacted.append(key)
                continue
            out[key] = entry.value
        return {"task_id": task_id, "clearance": clearance, "context": out, "redacted_keys": redacted}

    def status(self) -> Dict[str, Any]:
        return {"tasks": len(self._entries),
                "entries": sum(len(v) for v in self._entries.values())}
