"""Structured audit logging with secret redaction."""
from __future__ import annotations

import json
import logging
import threading
from typing import Any

from genesis.core import AuditEvent, new_id, now_ms
from genesis.security.redaction import Redactor

logger = logging.getLogger(__name__)


class AuditLogger:
    """In-memory + optional sink audit logger.

    Every record passes through a Redactor so secrets never reach the sink.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        sink=None,
        redactor: Redactor | None = None,
    ) -> None:
        self.enabled = enabled
        self._sink = sink
        self._redactor = redactor or Redactor()
        self._records: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record(
        self,
        event_type: str,
        actor: str,
        action: str,
        *,
        resource: str = "",
        status: str = "success",
        risk_level: str = "low",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_type=event_type,
            actor=actor,
            action=action,
            resource=resource,
            status=status,
            risk_level=risk_level,
            details=dict(details or {}),
        )
        self.record_event(event)
        return event

    def record_event(self, event: AuditEvent) -> AuditEvent:
        if not self.enabled:
            return event
        safe = json.loads(
            json.dumps(
                event.to_dict(),
                default=str,
            )
        )
        safe = self._redactor.redact_object(safe)  # type: ignore[assignment]
        with self._lock:
            self._records.append(safe)
            if self._sink is not None:
                try:
                    self._sink.write(safe)
                except Exception:  # noqa: BLE001
                    logger.exception("audit sink failed")
        return event

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)

    def count(self, event_type: str | None = None) -> int:
        with self._lock:
            if event_type is None:
                return len(self._records)
            return sum(1 for r in self._records if r.get("event_type") == event_type)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()