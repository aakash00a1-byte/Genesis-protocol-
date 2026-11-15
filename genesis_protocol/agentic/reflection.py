"""Experience and reflection for completed tasks (V7 P3).

After a task finishes, this module evaluates what happened and records what
worked, what failed and why. The output is evidence and lessons, not action.

Hard boundary (the "learning boundary"): a reflection may produce a
*recommendation* or a *planning note*, and it may store a lesson as an
explicitly-unverified hypothesis. It may NOT change code, widen a permission,
modify policy, alter trust, touch a secret or deploy. Any proposal of that kind
is produced as a :class:`LearningProposal` that is marked security-sensitive and
``applied=False``; only an owner can act on it, outside this engine.

A lesson is stored at ``verification="hypothesis"``. The engine never calls
``AgentMemory.verify`` and never writes ``verified``: an assumption cannot become
a verified fact here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.memory import AgentMemory, get_agent_memory
from genesis_protocol.agentic.tasks import TaskStore, get_task_store

# Proposals of these kinds may never be applied by the engine; they require an
# owner to act outside it.
SECURITY_SENSITIVE_KINDS = frozenset(
    {
        "code_change",
        "policy_change",
        "permission_change",
        "trust_change",
        "deploy",
        "secret_change",
        "settings_change",
    }
)

# Kinds the engine may *suggest* (still not apply).
ADVISORY_KINDS = frozenset({"recommendation", "planning_note"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LearningProposal:
    """A suggested change. Never applied by the engine."""

    kind: str
    summary: str
    evidence: List[str] = field(default_factory=list)
    security_sensitive: bool = False
    requires_owner_approval: bool = False
    applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Reflection:
    """The evaluation of one completed task."""

    task_id: Optional[str]
    user_id: int
    state: str
    what_worked: List[str] = field(default_factory=list)
    what_failed: List[str] = field(default_factory=list)
    why: List[str] = field(default_factory=list)
    lessons: List[str] = field(default_factory=list)
    proposals: List[LearningProposal] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "state": self.state,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "why": self.why,
            "lessons": self.lessons,
            "proposals": [p.to_dict() for p in self.proposals],
            "created_at": self.created_at,
        }


def make_proposal(kind: str, summary: str, evidence: Optional[List[str]] = None) -> LearningProposal:
    """Build a proposal, marking security-sensitive kinds as owner-required."""
    sensitive = kind in SECURITY_SENSITIVE_KINDS
    return LearningProposal(
        kind=kind,
        summary=summary,
        evidence=list(evidence or []),
        security_sensitive=sensitive,
        requires_owner_approval=sensitive,
        applied=False,
    )


class ReflectionEngine:
    """Turns a finished task into an evidence-based reflection and lessons."""

    def __init__(
        self,
        memory: Optional[AgentMemory] = None,
        tasks: Optional[TaskStore] = None,
        store_lessons: bool = True,
    ):
        self.memory = memory or get_agent_memory()
        self.tasks = tasks or get_task_store()
        self.store_lessons = store_lessons

    def reflect(
        self, user_id: int, task_id: Optional[str] = None, record: Optional[Dict[str, Any]] = None
    ) -> Reflection:
        """Evaluate a task and return a :class:`Reflection`.

        ``record`` may be supplied directly (a task dict); otherwise the task is
        loaded from the store. A task that is still running is reflected on as
        "incomplete" - no success is claimed for work that has not finished.
        """
        if record is None:
            if task_id is None:
                raise ValueError("reflect needs a task_id or a record")
            stored = self.tasks.get(user_id, task_id)
            if stored is None:
                raise ValueError(f"unknown task '{task_id}'")
            record = stored.to_dict()

        state = str(record.get("state", "unknown"))
        steps: List[Dict[str, Any]] = list(record.get("steps") or [])

        what_worked: List[str] = []
        what_failed: List[str] = []
        why: List[str] = []
        for step in steps:
            label = self._step_label(step)
            if step.get("success") is True:
                what_worked.append(label)
            elif step.get("success") is False:
                what_failed.append(label)
                reason = step.get("error") or step.get("reason") or "no reason recorded"
                why.append(f"{label}: {reason}")

        lessons: List[str] = []
        proposals: List[LearningProposal] = []

        if state == "completed" and not what_failed:
            lessons.append("Task completed with every recorded step succeeding.")
        elif what_failed:
            lessons.append(
                f"{len(what_failed)} step(s) failed; inspect the recorded reasons before retrying."
            )
            proposals.append(
                make_proposal(
                    "recommendation",
                    "Review the failed steps and adjust the plan before retrying.",
                    evidence=why,
                )
            )
        elif state in ("pending", "running", "paused"):
            lessons.append(f"Task is {state}; outcome is not yet determined, so no success is claimed.")
        elif state == "cancelled":
            lessons.append("Task was cancelled; no outcome to evaluate.")
        else:
            lessons.append(f"Task state '{state}' has no successful-outcome evidence.")

        reflection = Reflection(
            task_id=record.get("id", task_id),
            user_id=int(user_id),
            state=state,
            what_worked=what_worked,
            what_failed=what_failed,
            why=why,
            lessons=lessons,
            proposals=proposals,
        )

        if self.store_lessons:
            self._store_lessons(user_id, reflection)
        return reflection

    @staticmethod
    def _step_label(step: Dict[str, Any]) -> str:
        step_type = step.get("type") or step.get("step_type") or "step"
        tool = step.get("tool") or step.get("name") or ""
        detail = f" '{tool}'" if tool else ""
        return f"{step_type}{detail}"

    def _store_lessons(self, user_id: int, reflection: Reflection) -> List[str]:
        """Store lessons as hypotheses. Never verified, never an instruction."""
        ids: List[str] = []
        for lesson in reflection.lessons:
            try:
                ids.append(
                    self.memory.remember(
                        user_id,
                        lesson,
                        kind="lesson",
                        approved=True,
                        source="reflection",
                        verification="hypothesis",
                        confidence=0.4,
                        origin=reflection.task_id,
                        provenance={"task_id": reflection.task_id, "state": reflection.state},
                    )
                )
            except Exception:
                # A lesson that cannot be stored must not break reflection.
                continue
        return ids
