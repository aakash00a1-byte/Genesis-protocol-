"""Emergency kill switch (V7 P6).

One switch that stops every automatic defensive action immediately. When engaged,
the defence engine may still detect, classify, correlate, alert and record - but
it performs no action, automatic or otherwise, until an owner disengages it.

The switch is deliberately simple and fail-safe:

* State is a single boolean persisted to a small JSON file, so it survives a
  restart and is visible to every process.
* If the state file cannot be read, the switch reports **engaged** (fail closed).
* Engaging requires no special privilege (anyone can stop automation). Disengaging
  requires owner approval, so a non-owner cannot re-enable autonomy.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class KillSwitch:
    """A persisted, fail-closed emergency stop for automatic defence."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get("GLUTEN_KILL_SWITCH") or str(Path("data") / "guardian_killswitch.json")
        self.path = path
        self._lock = threading.Lock()
        self._memory: Optional[Dict[str, Any]] = None

    # -- persistence ----------------------------------------------------------

    def _read(self) -> Dict[str, Any]:
        if self.path == ":memory:":
            return dict(self._memory or {})
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except FileNotFoundError:
            return {}
        except Exception:
            # Unreadable/corrupt state must not be read as "safe to act".
            return {"engaged": True, "reason": "state file unreadable", "unreadable": True}
        return {}

    def _write(self, data: Dict[str, Any]) -> None:
        if self.path == ":memory:":
            self._memory = dict(data)
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # -- state ----------------------------------------------------------------

    def is_engaged(self) -> bool:
        """Whether automatic defence is stopped. Fail closed on any doubt."""
        with self._lock:
            state = self._read()
        if state.get("unreadable"):
            return True
        return bool(state.get("engaged", False))

    def engage(self, reason: str = "", actor: Optional[str] = None) -> Dict[str, Any]:
        """Stop automatic defence. Anyone may do this."""
        with self._lock:
            state = {
                "engaged": True,
                "reason": reason or "manual",
                "by": actor or "unknown",
                "changed_at": _utcnow(),
            }
            self._write(state)
            return state

    def disengage(self, owner_approved: bool, actor: Optional[str] = None,
                  reason: str = "") -> Dict[str, Any]:
        """Resume automatic defence. Owner approval is mandatory."""
        if not owner_approved:
            raise PermissionError("disengaging the kill switch requires owner approval")
        with self._lock:
            state = {
                "engaged": False,
                "reason": reason or "owner resumed",
                "by": actor or "owner",
                "changed_at": _utcnow(),
            }
            self._write(state)
            return state

    def status(self) -> Dict[str, Any]:
        with self._lock:
            state = self._read()
        if state.get("unreadable"):
            return {"engaged": True, "reason": "state file unreadable", "changed_at": None}
        return {
            "engaged": bool(state.get("engaged", False)),
            "reason": state.get("reason"),
            "by": state.get("by"),
            "changed_at": state.get("changed_at"),
        }


_default: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    global _default
    if _default is None:
        _default = KillSwitch()
    return _default
