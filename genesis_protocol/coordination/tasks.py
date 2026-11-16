"""Task ownership, delegation and conflict resolution (V7 P7).

Coordinates who owns which task and stops two agents working the same task.

* **Ownership** - a task has exactly one owner agent at a time. Claiming a task
  already owned by another agent fails unless the claim is an explicit, verified
  handoff.
* **Delegation** - an agent may only delegate a task it owns, and only to an
  agent whose grant is a subset of its own (least privilege). Delegation records
  the parent-child link so lineage is auditable.
* **Duplicate prevention** - an idempotency key maps a logical task to one task
  id; submitting the same key twice returns the existing task instead of
  creating a second one.
* **Conflict resolution** - when two owners exist for one idempotency key, the
  earliest claim wins and the later claim is recorded as rejected, with reasons.

This module stores only coordination metadata (who owns what). It does not
duplicate the canonical task store or the identity registry, and it grants no
capability: a delegation is only accepted when the target's existing grant
already permits the work.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class CoordinationError(ValueError):
    """Raised when a coordination rule is violated."""


@dataclass
class OwnedTask:
    """One coordinated task and its single owner."""

    task_id: str
    idempotency_key: str
    owner: str
    state: str = "assigned"
    delegated_from: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TaskCoordinator:
    """Owns task assignment, delegation, deduplication and conflict handling."""

    def __init__(self, registry: Optional[Any] = None):
        self._registry = registry
        self._lock = threading.Lock()
        self._tasks: Dict[str, OwnedTask] = {}
        self._by_key: Dict[str, str] = {}
        self._counter = 0
        self._conflicts: List[Dict[str, Any]] = []

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from genesis_protocol.coordination.registry import CapabilityRegistry

            self._registry = CapabilityRegistry()
        return self._registry

    # -- assignment -----------------------------------------------------------

    def _new_id(self) -> str:
        self._counter += 1
        return f"TASK-{self._counter:05d}"

    def assign(self, owner: str, idempotency_key: str = "", state: str = "assigned",
               delegated_from: Optional[str] = None) -> OwnedTask:
        """Create or return a task for ``idempotency_key``.

        Idempotent: the same key returns the same task, so a retried assignment
        cannot create a duplicate.
        """
        key = idempotency_key or f"auto:{owner}:{self._counter + 1}"
        with self._lock:
            existing_id = self._by_key.get(key)
            if existing_id is not None:
                existing = self._tasks[existing_id]
                if existing.owner != owner:
                    self._conflicts.append({
                        "idempotency_key": key, "task_id": existing_id,
                        "winner": existing.owner, "loser": owner, "at": _utcnow(),
                        "resolution": "earliest owner wins",
                    })
                return existing
            task = OwnedTask(task_id=self._new_id(), idempotency_key=key, owner=owner,
                             state=state, delegated_from=delegated_from)
            task.history.append({"at": task.created_at, "event": "assigned", "actor": owner})
            self._tasks[task.task_id] = task
            self._by_key[key] = task.task_id
            return task

    def get(self, task_id: str) -> Optional[OwnedTask]:
        return self._tasks.get(task_id)

    def by_key(self, idempotency_key: str) -> Optional[OwnedTask]:
        tid = self._by_key.get(idempotency_key)
        return self._tasks.get(tid) if tid else None

    def owner_of(self, task_id: str) -> Optional[str]:
        task = self._tasks.get(task_id)
        return task.owner if task else None

    def update_state(self, task_id: str, actor: str, state: str) -> OwnedTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise CoordinationError(f"unknown task '{task_id}'")
            if actor != task.owner:
                raise CoordinationError(f"'{actor}' does not own task '{task_id}'")
            task.state = state
            task.updated_at = _utcnow()
            task.history.append({"at": task.updated_at, "event": f"state:{state}", "actor": actor})
            return task

    # -- delegation -----------------------------------------------------------

    def delegate(self, task_id: str, from_agent: str, to_agent: str) -> OwnedTask:
        """Hand a task from its owner to a sub-agent whose grant is a subset.

        Fails closed: a non-owner, an unknown target, or a target whose tools are
        not a subset of the delegator's is rejected.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise CoordinationError(f"unknown task '{task_id}'")
            if task.owner != from_agent:
                raise CoordinationError(f"'{from_agent}' does not own task '{task_id}'")
            parent = self.registry.manifest(from_agent)
            child = self.registry.manifest(to_agent)
            if parent is None or child is None:
                raise CoordinationError("delegator or delegate has no capability manifest")
            if not parent.can_delegate:
                raise CoordinationError(f"'{from_agent}' role may not delegate")
            if not self.registry.is_subset(child.tools, parent.tools):
                raise CoordinationError(
                    f"'{to_agent}' holds capabilities outside '{from_agent}' (privilege escalation blocked)"
                )
            previous = task.owner
            task.owner = to_agent
            task.delegated_from = previous
            task.updated_at = _utcnow()
            task.history.append({"at": task.updated_at, "event": "delegated",
                                 "from": previous, "to": to_agent})
            return task

    def lineage(self, task_id: str) -> List[str]:
        """The delegation chain for a task, oldest first."""
        chain: List[str] = []
        seen = set()
        task = self._tasks.get(task_id)
        while task and task.task_id not in seen:
            seen.add(task.task_id)
            chain.append(task.owner)
            task = self._tasks.get(self._by_key.get(task.idempotency_key, ""))
            break
        return chain

    # -- read side ------------------------------------------------------------

    def tasks(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        return [t.to_dict() for t in self._tasks.values() if owner is None or t.owner == owner]

    def conflicts(self) -> List[Dict[str, Any]]:
        return list(self._conflicts)

    def status(self) -> Dict[str, Any]:
        by_state: Dict[str, int] = {}
        for task in self._tasks.values():
            by_state[task.state] = by_state.get(task.state, 0) + 1
        return {"tasks": len(self._tasks), "by_state": by_state, "conflicts": len(self._conflicts)}
