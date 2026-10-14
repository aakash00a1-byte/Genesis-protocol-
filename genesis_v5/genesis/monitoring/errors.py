"""Bounded in-memory error tracking with secret redaction."""
from __future__ import annotations

import threading
import time
from typing import Any

from genesis.security.redaction import Redactor


class ErrorTracker:
    """Records structured errors with redaction; bounded ring buffer.

    Never logs raw secrets: every record passes through the Redactor.
    """

    def __init__(self, max_events: int = 200, redactor: Redactor | None = None) -> None:
        self.max_events = max(1, max_events)
        self._redactor = redactor or Redactor()
        self._events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(
        self,
        *,
        kind: str,
        message: str,
        component: str = "unknown",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "kind": kind,
            "message": message,
            "component": component,
            "ts_ms": int(time.time() * 1000),
            "details": dict(details or {}),
        }
        safe = self._redactor.redact_object(event)  # type: ignore[assignment]
        with self._lock:
            self._events.append(safe)  # type: ignore[arg-type]
            self._events = self._events[-self.max_events :]
        return event

    def recent(self, kind: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
        if kind is None:
            return events
        return [e for e in events if e.get("kind") == kind]

    def count(self, kind: str | None = None) -> int:
        return len(self.recent(kind))

    def clear(self) -> None:
        with self._lock:
            self._events.clear()