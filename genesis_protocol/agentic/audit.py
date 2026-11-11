"""Append-only audit log for agent tool requests.

Every tool request - allowed or denied - is recorded with who asked, what was
requested, the decision and why. The log is JSONL so it is greppable and easy
to ship, and it never contains tool arguments verbatim (which could hold
secrets): only a redacted, truncated summary.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_REDACT = re.compile(
    r"(?i)((?:api[_-]?key|token|secret|password|passwd|bearer)['\"]?\s*[:=]\s*['\"]?)([^'\"]+|\S+)"
)


def _redact(text: str, limit: int = 200) -> str:
    text = _REDACT.sub(r"\1<redacted>", str(text))
    return text[:limit]


class AuditLog:
    """JSONL audit sink. One line per decision."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get("GLUTEN_AUDIT_LOG") or str(Path("data") / "gluten_audit.jsonl")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory: list = []

    def record(
        self,
        event: str,
        user_id: Optional[int] = None,
        tool: Optional[str] = None,
        allowed: Optional[bool] = None,
        reason: str = "",
        detail: Any = None,
    ) -> Dict[str, Any]:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "user_id": user_id,
            "tool": tool,
            "allowed": allowed,
            "reason": reason,
        }
        if detail is not None:
            entry["detail"] = _redact(json.dumps(detail, default=str))
        with self._lock:
            if self.path == ":memory:":
                self._memory.append(entry)
            else:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entry) + "\n")
        return entry

    def tail(self, limit: int = 50) -> list:
        """Return the most recent entries (in-memory sink or file)."""
        if self.path == ":memory:":
            return self._memory[-limit:]
        if not Path(self.path).exists():
            return []
        with self._lock:
            lines = Path(self.path).read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out


_default: Optional[AuditLog] = None


def get_audit_log() -> AuditLog:
    global _default
    if _default is None:
        _default = AuditLog()
    return _default
