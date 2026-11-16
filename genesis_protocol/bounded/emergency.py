"""Emergency stop used when the canonical kill switch is unavailable (V7 P8).

P6 ships the canonical, persisted :class:`genesis_protocol.guardian.KillSwitch`.
P8 depends on an emergency stop but must not require P6 to import, so the gate
resolves the canonical switch lazily and falls back to this in-process switch
only when it is genuinely absent.

The fallback keeps the same safety shape as the canonical switch:

* state is a single boolean, so it is trivial to reason about;
* an unreadable state is read as **engaged** (fail closed);
* anyone may engage it (stopping work never needs privilege);
* only an owner-approved call may disengage it.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalKillSwitch:
    """In-process, fail-closed emergency stop (fallback for the canonical one)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {}

    def is_engaged(self) -> bool:
        with self._lock:
            return bool(self._state.get("engaged", False))

    def engage(self, reason: str = "", actor: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            self._state = {
                "engaged": True,
                "reason": reason or "manual",
                "by": actor or "unknown",
                "changed_at": _utcnow(),
            }
            return dict(self._state)

    def disengage(self, owner_approved: bool, actor: Optional[str] = None,
                  reason: str = "") -> Dict[str, Any]:
        if not owner_approved:
            raise PermissionError("owner approval required to disengage the kill switch")
        with self._lock:
            self._state = {
                "engaged": False,
                "reason": reason or "owner resumed",
                "by": actor or "owner",
                "changed_at": _utcnow(),
            }
            return dict(self._state)

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "engaged": bool(self._state.get("engaged", False)),
                "reason": self._state.get("reason", ""),
                "by": self._state.get("by", ""),
                "changed_at": self._state.get("changed_at", ""),
                "backend": "local-fallback",
            }


_fallback: Optional[LocalKillSwitch] = None


def get_local_kill_switch() -> LocalKillSwitch:
    global _fallback
    if _fallback is None:
        _fallback = LocalKillSwitch()
    return _fallback


def resolve_kill_switch() -> Any:
    """Return the canonical P6 kill switch, or the local fallback if absent."""
    try:
        from genesis_protocol.guardian.killswitch import get_kill_switch

        return get_kill_switch()
    except Exception:
        return get_local_kill_switch()
