"""Durable task state and execution history for GLUTEN.

A task is a small state machine that survives restarts. Each step of the agent
loop appends to the task's history, so a failed task can be inspected and a
partially-completed task can be resumed without redoing finished steps.

This is deliberately not a background scheduler: nothing here runs on a timer
or a daemon. Execution is driven by a caller. Resumption is explicit. Claiming
background autonomy without a real scheduler would be a false claim.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TASK_STATES = ("pending", "running", "paused", "completed", "failed", "cancelled")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskRecord:
    id: str
    user_id: int
    goal: str
    state: str = "pending"
    steps: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskRecord":
        return cls(**data)


class TaskStore:
    """JSON-file task store. Thread-safe, durable across restarts."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get("GLUTEN_TASK_DB") or str(Path("data") / "gluten_tasks.json")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._load()

    def _load(self) -> None:
        if self.path == ":memory:" or not Path(self.path).exists():
            return
        try:
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in raw.get("tasks", []):
            try:
                record = TaskRecord.from_dict(item)
                self._tasks[record.id] = record
            except (TypeError, KeyError):
                continue

    def _save(self) -> None:
        if self.path == ":memory:":
            return
        payload = {"tasks": [t.to_dict() for t in self._tasks.values()]}
        tmp = Path(self.path).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)  # atomic swap so a crash cannot truncate state

    # -- lifecycle ------------------------------------------------------------

    def create(self, user_id: int, goal: str) -> TaskRecord:
        record = TaskRecord(id=uuid.uuid4().hex[:12], user_id=int(user_id), goal=goal)
        with self._lock:
            self._tasks[record.id] = record
            self._save()
        return record

    def get(self, user_id: int, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
        if record and record.user_id == int(user_id):
            return record
        return None  # isolation: another user's task is invisible

    def list_tasks(self, user_id: int, state: Optional[str] = None) -> List[TaskRecord]:
        with self._lock:
            records = [t for t in self._tasks.values() if t.user_id == int(user_id)]
        if state:
            records = [t for t in records if t.state == state]
        return sorted(records, key=lambda t: t.updated_at, reverse=True)

    def append_step(self, user_id: int, task_id: str, step: Dict[str, Any]) -> TaskRecord:
        """Append one executed step to a task's history and persist."""
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.user_id != int(user_id):
                raise KeyError("task not found")
            record.steps.append({**step, "ts": _utcnow()})
            record.updated_at = _utcnow()
            self._save()
            return record

    def set_state(
        self, user_id: int, task_id: str, state: str, error: Optional[str] = None
    ) -> TaskRecord:
        if state not in TASK_STATES:
            raise ValueError(f"invalid state '{state}'")
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None or record.user_id != int(user_id):
                raise KeyError("task not found")
            record.state = state
            record.error = error
            record.updated_at = _utcnow()
            self._save()
            return record

    def resume_point(self, user_id: int, task_id: str) -> int:
        """Index of the first step that still needs to run.

        The latest outcome for each step index decides whether it is done: a
        step that succeeded on a retry counts as done, and only the first step
        whose latest outcome failed (and everything after it) is re-run.
        """
        record = self.get(user_id, task_id)
        if record is None:
            raise KeyError("task not found")
        latest: Dict[int, bool] = {}
        for step in record.steps:
            if "index" in step:
                latest[int(step["index"])] = bool(step.get("success"))
        completed = 0
        while latest.get(completed) is True:
            completed += 1
        return completed

    def close(self) -> None:  # parity with other stores
        return None


_default: Optional[TaskStore] = None


def get_task_store(path: Optional[str] = None) -> TaskStore:
    global _default
    if path is None:
        path = os.environ.get("GLUTEN_TASK_DB") or str(Path("data") / "gluten_tasks.json")
    if _default is None or _default.path != path:
        _default = TaskStore(path)
    return _default
