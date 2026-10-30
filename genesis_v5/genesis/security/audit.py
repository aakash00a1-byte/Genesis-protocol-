"""Structured audit logging with secret redaction and tamper-evidence.

Records form a hash chain: each record stores its sequence number, the hash of
the previous record and its own hash. Changing, deleting or reordering a
record breaks the chain, so ``verify_chain`` can point at the first bad index.

This is tamper-*evident*, not tamper-*proof*: a writer who can rewrite the
whole list can recompute a fresh valid chain. To detect that, hand a
``checkpoint`` to an independent store (see ``verify_checkpoint``); the chain
alone only proves internal consistency.
"""
from __future__ import annotations

import hashlib
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
    Records are hash-chained for tamper-evidence.
    """

    GENESIS_HASH = "0" * 64

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

    @staticmethod
    def _compute_hash(record: dict[str, Any]) -> str:
        """Hash a record's content, excluding its own ``hash`` field.

        ``sort_keys`` makes the digest independent of dict insertion order, so
        a legitimate re-serialization is not mistaken for tampering.
        """
        content = {k: v for k, v in record.items() if k != "hash"}
        blob = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

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
            seq = len(self._records)
            prev_hash = self._records[-1]["hash"] if self._records else self.GENESIS_HASH
            safe["seq"] = seq
            safe["prev_hash"] = prev_hash
            safe["hash"] = self._compute_hash(safe)
            self._records.append(safe)
            if self._sink is not None:
                try:
                    self._sink.write(safe)
                except Exception:  # noqa: BLE001
                    logger.exception("audit sink failed")
        return event

    def events(self) -> list[dict[str, Any]]:
        with self._lock:
            # Deep copy so a caller cannot mutate the stored chain.
            return json.loads(json.dumps(self._records, default=str))

    def count(self, event_type: str | None = None) -> int:
        with self._lock:
            if event_type is None:
                return len(self._records)
            return sum(1 for r in self._records if r.get("event_type") == event_type)

    def verify_chain(self) -> tuple[bool, int | None, str]:
        """Return ``(ok, first_bad_index, reason)``.

        Walks the chain from the start. A record whose stored ``hash`` does not
        match its content, whose ``seq`` is out of order, or whose ``prev_hash``
        does not match the previous record's hash is reported as the first
        inconsistency. ``ok`` is True only for a fully intact chain.
        """
        with self._lock:
            records = json.loads(json.dumps(self._records, default=str))
        prev_hash = self.GENESIS_HASH
        for index, record in enumerate(records):
            if record.get("seq") != index:
                return False, index, f"missing or reordered record at index {index}"
            if record.get("prev_hash") != prev_hash:
                return False, index, f"broken chain link at index {index}"
            if record.get("hash") != self._compute_hash(record):
                return False, index, f"modified record at index {index}"
            prev_hash = record["hash"]
        return True, None, ""

    def checkpoint(self) -> dict[str, Any]:
        """Return a compact commitment to the current chain head.

        Store this somewhere the agent cannot rewrite. Recomputing a valid
        chain after tampering cannot match a checkpoint held elsewhere.
        """
        with self._lock:
            count = len(self._records)
            head_hash = self._records[-1]["hash"] if self._records else self.GENESIS_HASH
        return {"count": count, "head_hash": head_hash}

    def verify_checkpoint(self, checkpoint: dict[str, Any]) -> bool:
        """True if the current chain still matches ``checkpoint``."""
        return self.checkpoint() == checkpoint

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
