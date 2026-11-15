"""Reversible sinks for automatic defensive actions (V7 P6).

The defence engine performs low-risk actions through a sink. A sink must satisfy
two properties:

* **Reversible** - every action returns a rollback token and can be undone.
* **Narrowing** - an action may only *reduce* what a target can do, never grant,
  escalate or destroy. All three actions below only add a cooldown entry or a
  notification.

``LocalActionSink`` keeps a small JSON ledger of temporary cooldowns. Other
components (the web layer) may consult ``is_throttled`` to enforce them. The
ledger is bounded and each entry expires, so a stale entry cannot accumulate.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from genesis_protocol.guardian.actions import ActionCatalog, ActionNotAllowed


def _now() -> float:
    return time.time()


class LocalActionSink:
    """Performs reversible low-risk defensive actions against a local ledger."""

    def __init__(
        self,
        path: Optional[str] = None,
        cooldown_seconds: float = 900.0,
        max_entries: int = 500,
        catalog: Optional[ActionCatalog] = None,
    ):
        if path is None:
            path = os.environ.get("GLUTEN_DEFENCE_LEDGER") or str(Path("data") / "guardian_defence.json")
        self.path = path
        self.cooldown_seconds = cooldown_seconds
        self.max_entries = max_entries
        self.catalog = catalog or ActionCatalog()
        self._lock = threading.Lock()
        self._memory: Optional[Dict[str, Any]] = None

    # -- ledger ---------------------------------------------------------------

    def _load(self) -> Dict[str, Any]:
        if self.path == ":memory:":
            return dict(self._memory or {"entries": {}, "notifications": []})
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict) and "entries" in data:
                    return data
        except FileNotFoundError:
            return {"entries": {}, "notifications": []}
        except Exception:
            # A corrupt ledger must not be trusted; start empty rather than crash.
            return {"entries": {}, "notifications": []}
        return {"entries": {}, "notifications": []}

    def _save(self, data: Dict[str, Any]) -> None:
        # Drop expired entries, then cap the size (keep the newest).
        entries = {k: v for k, v in data.get("entries", {}).items()
                   if float(v.get("expires_at", 0)) > _now()}
        if len(entries) > self.max_entries:
            newest = sorted(entries.items(), key=lambda kv: kv[1].get("expires_at", 0), reverse=True)
            entries = dict(newest[: self.max_entries])
        data = {"entries": entries, "notifications": data.get("notifications", [])[-100:]}
        if self.path == ":memory:":
            self._memory = data
            return
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        os.replace(tmp, self.path)

    # -- actions --------------------------------------------------------------

    def __call__(self, action: str, target: Optional[str], incident: Any) -> Optional[str]:
        """Perform a low-risk action; return a rollback token (or None)."""
        if not self.catalog.is_automatic_allowed(action):
            raise ActionNotAllowed(f"'{action}' is not an automatic low-risk action")
        if not target and action != "raise_alert":
            raise ValueError(f"action '{action}' requires a target")

        with self._lock:
            data = self._load()
            if action in ("rate_limit_actor", "throttle_source"):
                key = f"{action}:{target}"
                token = f"cd-{int(_now())}-{target}"
                data.setdefault("entries", {})[key] = {
                    "action": action,
                    "target": target,
                    "token": token,
                    "created_at": _now(),
                    "expires_at": _now() + self.cooldown_seconds,
                    "incident_id": getattr(incident, "incident_id", None),
                }
                self._save(data)
                return token
            if action == "raise_alert":
                token = f"nt-{int(_now())}"
                data.setdefault("notifications", []).append({
                    "token": token,
                    "created_at": _now(),
                    "incident_id": getattr(incident, "incident_id", None),
                })
                self._save(data)
                return token
        raise ActionNotAllowed(f"no sink implementation for '{action}'")

    def rollback(self, action: str, target: Optional[str], token: Optional[str] = None) -> bool:
        """Undo a performed action. Returns True if something was undone."""
        if not self.catalog.allowed(action):
            raise ActionNotAllowed(f"cannot roll back non-permitted action '{action}'")
        with self._lock:
            data = self._load()
            if action in ("rate_limit_actor", "throttle_source"):
                key = f"{action}:{target}"
                removed = data.get("entries", {}).pop(key, None) is not None
                self._save(data)
                return removed
            if action == "raise_alert":
                before = len(data.get("notifications", []))
                data["notifications"] = [n for n in data.get("notifications", []) if n.get("token") != token]
                self._save(data)
                return len(data["notifications"]) != before
        return False

    # -- read side ------------------------------------------------------------

    def is_throttled(self, target: str, action: Optional[str] = None) -> bool:
        """Whether ``target`` currently has an active cooldown."""
        if not target:
            return False
        with self._lock:
            data = self._load()
        for key, entry in data.get("entries", {}).items():
            if entry.get("target") != target:
                continue
            if action and entry.get("action") != action:
                continue
            if float(entry.get("expires_at", 0)) > _now():
                return True
        return False

    def status(self) -> Dict[str, Any]:
        with self._lock:
            data = self._load()
        active = {k: v for k, v in data.get("entries", {}).items() if float(v.get("expires_at", 0)) > _now()}
        return {
            "active_cooldowns": len(active),
            "notifications": len(data.get("notifications", [])),
            "cooldown_seconds": self.cooldown_seconds,
        }
