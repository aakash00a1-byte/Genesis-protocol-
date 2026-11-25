"""Mission planning and task decomposition (V7 P10).

A *mission* is a goal too large for one step. P10 plans it, then decomposes it
into a DAG of tasks with explicit dependencies, so progress, replanning and
verification all have something concrete to reason about.

Decomposition is deterministic: it expands each goal clause into a task, links
sequential phases, and records the success criterion for each task. It does not
execute anything and it does not invent facts - a task's ``acceptance`` is a
statement the result must satisfy, checked later by ``verification``.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_SKIPPED = "skipped"

MAX_TASKS = 64
_CLAUSE_SPLIT = re.compile(r"[.;\n]+|(?:\band then\b)|(?:\bthen\b)", re.IGNORECASE)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MissionTask:
    """One decomposed unit of a mission."""

    task_id: str
    goal: str
    depends_on: List[str] = field(default_factory=list)
    acceptance: str = ""
    status: str = STATUS_PENDING
    assigned_to: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    attempts: int = 0
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Mission:
    """A planned goal with a task DAG."""

    mission_id: str
    goal: str
    tasks: List[MissionTask] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow)
    owner_id: Optional[int] = None
    status: str = STATUS_PENDING
    revision: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    budget: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        budget = self.budget
        if budget is not None and hasattr(budget, "__dataclass_fields__"):
            budget = asdict(budget)
        return {
            "mission_id": self.mission_id,
            "goal": self.goal,
            "status": self.status,
            "revision": self.revision,
            "owner_id": self.owner_id,
            "created_at": self.created_at,
            "budget": budget,
            "tasks": [t.to_dict() for t in self.tasks],
            "history": list(self.history),
        }

    def task(self, task_id: str) -> Optional[MissionTask]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def ready_tasks(self) -> List[MissionTask]:
        done = {t.task_id for t in self.tasks if t.status in (STATUS_DONE, STATUS_SKIPPED)}
        return [
            t for t in self.tasks
            if t.status in (STATUS_PENDING, STATUS_READY)
            and all(dep in done for dep in t.depends_on)
        ]

    def blocked_tasks(self) -> List[MissionTask]:
        done = {t.task_id for t in self.tasks if t.status in (STATUS_DONE, STATUS_SKIPPED)}
        return [
            t for t in self.tasks
            if t.status in (STATUS_PENDING, STATUS_READY)
            and any(dep not in done for dep in t.depends_on)
        ]

    def has_cycle(self) -> bool:
        """True when the dependency graph is not a DAG."""
        graph = {t.task_id: list(t.depends_on) for t in self.tasks}
        visiting: set = set()
        visited: set = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for dep in graph.get(node, []):
                if dep in graph and visit(dep):
                    return True
            visiting.discard(node)
            visited.add(node)
            return False

        return any(visit(n) for n in list(graph))


def _after_marker(clause: str) -> Optional[tuple[List[str], str]]:
    """Parse a leading ``after: t1, t2 - goal`` marker.

    Hand-rolled rather than a regex: ``([^,]+(?:,[^,]+)*)`` is the kind of nested
    quantifier that backtracks polynomially. Returns ``(depends, goal)`` or
    ``None`` when the clause has no usable marker.
    """
    if not clause.lower().startswith("after:"):
        return None
    rest = clause[len("after:"):]
    for position, char in enumerate(rest):
        if char in "-:":
            if position == 0:
                return None
            names = [name.strip() for name in rest[:position].split(",") if name.strip()]
            goal = rest[position + 1:].strip()
            if names and goal:
                return names, goal
            return None
    return None


def decompose(goal: str, acceptance: str = "") -> List[Dict[str, Any]]:
    """Turn a goal into an ordered list of ``{goal, depends_on, acceptance}``.

    Sequential clauses become chained tasks; a clause may name its predecessors
    with a leading ``after: t1, t2`` marker. Deterministic and side-effect free.
    """
    clauses = [c.strip(" -\t") for c in _CLAUSE_SPLIT.split(goal or "") if c.strip()]
    if not clauses:
        raise ValueError("a mission needs a non-empty goal")
    if len(clauses) > MAX_TASKS:
        raise ValueError(f"mission decomposes into too many tasks ({len(clauses)} > {MAX_TASKS})")

    tasks: List[Dict[str, Any]] = []
    for index, clause in enumerate(clauses):
        depends: List[str] = []
        parsed = _after_marker(clause)
        if parsed is not None:
            depends, clause = parsed
        elif index > 0:
            depends = [f"t{index}"]  # chain to the previous clause
        tasks.append({
            "task_id": f"t{index + 1}",
            "goal": clause,
            "depends_on": depends,
            "acceptance": acceptance if index == len(clauses) - 1 else "",
        })
    return tasks


def plan(mission_id: str, goal: str, owner_id: Optional[int] = None,
         acceptance: str = "") -> Mission:
    """Build a :class:`Mission` with a validated task DAG."""
    mission = Mission(mission_id=mission_id, goal=goal.strip(), owner_id=owner_id)
    for spec in decompose(goal, acceptance=acceptance):
        mission.tasks.append(MissionTask(
            task_id=spec["task_id"],
            goal=spec["goal"],
            depends_on=spec["depends_on"],
            acceptance=spec["acceptance"],
        ))
    known = {t.task_id for t in mission.tasks}
    for task in mission.tasks:
        unknown = [d for d in task.depends_on if d not in known]
        if unknown:
            raise ValueError(f"task {task.task_id} depends on unknown {unknown}")
    if mission.has_cycle():
        raise ValueError("mission task graph contains a cycle")
    mission.history.append({"at": utcnow(), "event": "planned",
                            "tasks": len(mission.tasks)})
    return mission
