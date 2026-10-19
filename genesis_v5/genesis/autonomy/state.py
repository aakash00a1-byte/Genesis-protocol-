"""Persistent task state and resumable checkpoints for the autonomy loop.

State is written as JSON under a checkpoint directory, one file per run
(``<run_id>.json``). Writes are atomic (temp file + ``os.replace``) so an
interrupted run never leaves a half-written checkpoint behind. Every value is
redacted on the way to disk, so a secret that reached a task field cannot leak
into a checkpoint.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.core import new_id, now_ms, redact_value


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    VERIFYING = "verifying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    LIMIT_REACHED = "limit_reached"
    BLOCKED = "blocked"


# Terminal states never resume. FAILED is deliberately *not* terminal: the
# task requires failures to remain recoverable, so a failed run can be
# resumed after the underlying problem is fixed. Only a completed run
# (SUCCEEDED) or an outright refusal (BLOCKED) is terminal.
_TERMINAL = {
    TaskStatus.SUCCEEDED,
    TaskStatus.BLOCKED,
}


@dataclass
class Checkpoint:
    """A single resumable marker within a run."""

    iteration: int
    status: str
    result: Any = None
    errors: list[str] = field(default_factory=list)
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "status": self.status,
            "result": self.result,
            "errors": list(self.errors),
            "ts_ms": self.ts_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        return cls(
            iteration=int(data.get("iteration", 0)),
            status=str(data.get("status", "")),
            result=data.get("result"),
            errors=list(data.get("errors", [])),
            ts_ms=int(data.get("ts_ms", now_ms())),
        )


@dataclass
class TaskState:
    """The full, persisted state of one autonomous run."""

    run_id: str = field(default_factory=lambda: new_id("run"))
    task: str = ""
    actor: str = "autonomy"
    role: str = "coder"
    status: TaskStatus = TaskStatus.PENDING
    iteration: int = 0
    attempts: int = 0
    started_ms: int = field(default_factory=now_ms)
    updated_ms: int = field(default_factory=now_ms)
    result: Any = None
    errors: list[str] = field(default_factory=list)
    checkpoints: list[Checkpoint] = field(default_factory=list)
    audit_ids: list[str] = field(default_factory=list)
    blocked_reason: str = ""
    # Read-only reconnaissance outcomes (tool -> status), for transparency.
    recon: dict[str, Any] = field(default_factory=dict)

    def add_checkpoint(
        self,
        *,
        status: TaskStatus,
        result: Any = None,
        errors: list[str] | None = None,
    ) -> Checkpoint:
        self.status = status
        self.updated_ms = now_ms()
        if errors:
            self.errors.extend(errors)
        cp = Checkpoint(
            iteration=self.iteration,
            status=status.value,
            result=result,
            errors=list(errors or []),
        )
        self.checkpoints.append(cp)
        return cp

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task": self.task,
            "actor": self.actor,
            "role": self.role,
            "status": self.status.value,
            "iteration": self.iteration,
            "attempts": self.attempts,
            "started_ms": self.started_ms,
            "updated_ms": self.updated_ms,
            "result": self.result,
            "errors": list(self.errors),
            "checkpoints": [c.to_dict() for c in self.checkpoints],
            "audit_ids": list(self.audit_ids),
            "blocked_reason": self.blocked_reason,
            "recon": dict(self.recon),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState:
        return cls(
            run_id=str(data.get("run_id", new_id("run"))),
            task=str(data.get("task", "")),
            actor=str(data.get("actor", "autonomy")),
            role=str(data.get("role", "coder")),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
            iteration=int(data.get("iteration", 0)),
            attempts=int(data.get("attempts", 0)),
            started_ms=int(data.get("started_ms", now_ms())),
            updated_ms=int(data.get("updated_ms", now_ms())),
            result=data.get("result"),
            errors=list(data.get("errors", [])),
            checkpoints=[
                Checkpoint.from_dict(c) for c in data.get("checkpoints", [])
            ],
            audit_ids=list(data.get("audit_ids", [])),
            blocked_reason=str(data.get("blocked_reason", "")),
            recon=dict(data.get("recon", {})),
        )

    @property
    def resumable(self) -> bool:
        """True when the run was interrupted and can continue."""
        return self.status not in _TERMINAL


class TaskStore:
    """Atomic, redacting, JSON-on-disk store for run state."""

    def __init__(self, directory: str) -> None:
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def _path(self, run_id: str) -> str:
        # run_id is generated by new_id(); guard against path traversal anyway.
        safe = "".join(c for c in run_id if c.isalnum() or c in "-_")
        return os.path.join(self.directory, f"{safe}.json")

    def path_for(self, run_id: str) -> str:
        """Public accessor for a run's checkpoint path."""
        return self._path(run_id)

    def save(self, state: TaskState) -> str:
        """Persist atomically. Returns the file path."""
        path = self._path(state.run_id)
        payload = redact_value(state.to_dict())
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        return path

    def load(self, run_id: str) -> TaskState | None:
        path = self._path(run_id)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as handle:
            return TaskState.from_dict(json.load(handle))

    def exists(self, run_id: str) -> bool:
        return os.path.exists(self._path(run_id))

    def list_runs(self) -> list[str]:
        return sorted(
            f[: -len(".json")]
            for f in os.listdir(self.directory)
            if f.endswith(".json")
        )
