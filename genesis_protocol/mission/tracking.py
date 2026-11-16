"""Progress tracking and replanning (V7 P10).

Tracking answers *where is the mission now?* and *is it stuck?*. Replanning
answers *what changes when reality disagrees with the plan?* - a failed or
blocked task can be replaced by new tasks, the mission is re-versioned, and the
change is recorded in the mission history so the plan stays explainable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from genesis_protocol.mission.planner import (
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    Mission,
    MissionTask,
    utcnow,
)

_TERMINAL = {STATUS_DONE, STATUS_FAILED, STATUS_SKIPPED}


@dataclass
class Progress:
    total: int
    done: int
    failed: int
    skipped: int
    running: int
    ready: int
    blocked: int
    pending: int
    percent: float
    stalled: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total, "done": self.done, "failed": self.failed,
            "skipped": self.skipped, "running": self.running, "ready": self.ready,
            "blocked": self.blocked, "pending": self.pending,
            "percent": round(self.percent, 2), "stalled": self.stalled,
        }


def progress(mission: Mission) -> Progress:
    counts = {STATUS_PENDING: 0, STATUS_READY: 0, STATUS_RUNNING: 0,
              STATUS_DONE: 0, STATUS_FAILED: 0, STATUS_BLOCKED: 0, STATUS_SKIPPED: 0}
    for task in mission.tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    total = len(mission.tasks)
    finished = counts[STATUS_DONE] + counts[STATUS_SKIPPED]
    percent = (finished / total * 100.0) if total else 0.0
    # Stalled: work remains, nothing is running, and nothing is ready to run.
    stalled = bool(
        total
        and counts[STATUS_RUNNING] == 0
        and counts[STATUS_READY] == 0
        and (counts[STATUS_PENDING] or counts[STATUS_BLOCKED])
        and finished < total
    )
    return Progress(
        total=total,
        done=counts[STATUS_DONE],
        failed=counts[STATUS_FAILED],
        skipped=counts[STATUS_SKIPPED],
        running=counts[STATUS_RUNNING],
        ready=counts[STATUS_READY],
        blocked=counts[STATUS_BLOCKED],
        pending=counts[STATUS_PENDING],
        percent=percent,
        stalled=stalled,
    )


class Replanner:
    """Revises a mission when a task fails or the goal changes."""

    def __init__(self, mission: Mission):
        self.mission = mission

    def replace_failed(self, task_id: str, new_goals: List[str],
                       reason: str = "") -> List[MissionTask]:
        """Replace a failed/blocked task with new tasks that inherit its place.

        The new tasks take over the failed task's dependents and depend on the
        failed task's dependencies, so the DAG stays valid. The failed task is
        marked ``skipped`` (it is no longer part of the path) and the mission is
        re-versioned.
        """
        failed = self.mission.task(task_id)
        if failed is None:
            raise KeyError(f"unknown task '{task_id}'")
        if failed.status not in (STATUS_FAILED, STATUS_BLOCKED, STATUS_PENDING):
            raise ValueError(f"task '{task_id}' is '{failed.status}', not replannable")
        if not new_goals:
            raise ValueError("replanning needs at least one replacement task")

        created: List[MissionTask] = []
        previous = None
        for offset, goal in enumerate(new_goals):
            task = MissionTask(
                task_id=f"{task_id}r{offset + 1}",
                goal=goal.strip(),
                depends_on=list(failed.depends_on) if offset == 0 else [previous.task_id],
                acceptance=failed.acceptance,
            )
            self.mission.tasks.append(task)
            created.append(task)
            previous = task

        # Dependents now wait on the last replacement instead of the failed task.
        for task in self.mission.tasks:
            if task_id in task.depends_on:
                task.depends_on = [d for d in task.depends_on if d != task_id]
                task.depends_on.append(previous.task_id)

        failed.status = STATUS_SKIPPED
        failed.updated_at = utcnow()
        self.mission.revision += 1
        self.mission.history.append({
            "at": utcnow(), "event": "replanned", "replaced": task_id,
            "revision": self.mission.revision,
            "new_tasks": [t.task_id for t in created], "reason": reason,
        })
        return created

    def add_tasks(self, goals: List[str], after: Optional[List[str]] = None,
                  reason: str = "") -> List[MissionTask]:
        """Append new tasks to a mission (e.g. the goal was extended)."""
        created: List[MissionTask] = []
        previous = (after or [None])[-1]
        for offset, goal in enumerate(goals):
            task = MissionTask(
                task_id=f"a{self.mission.revision}-{len(self.mission.tasks) + 1}",
                goal=goal.strip(),
                depends_on=[previous] if previous else list(after or []),
            )
            self.mission.tasks.append(task)
            created.append(task)
            previous = task.task_id
        self.mission.revision += 1
        self.mission.history.append({
            "at": utcnow(), "event": "extended", "revision": self.mission.revision,
            "new_tasks": [t.task_id for t in created], "reason": reason,
        })
        return created
