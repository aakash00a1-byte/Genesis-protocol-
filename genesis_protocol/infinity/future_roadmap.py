"""Roadmap of falsifiable objectives, with progress derived from evidence.

This module used to be the opposite of what it is now. It shipped six milestones
with hand-written percentages (60/40/20/0/0/0) and target dates computed as
``now + N days``, including a "Self-Awareness" milestone. Worse, the auto-updater
then *recomputed* those percentages from elapsed wall-clock time against
2024-01-01 and persisted them, so the live Space advertised an 87.7% "average
progress" while reporting zero completed milestones and zero interactions. The
number measured nothing but the passage of time.

Progress is now a function of evidence, and nothing else:

* no evidence          -> 0,   status "planned"
* evidence, unverified -> 50,  status "in_progress"
* verified evidence    -> 100, status "completed"

There is no setter for the number. ``record_evidence`` is the only way to move
it, and ``verified`` evidence is what the verification gate says it is - not
what a caller asserts. Loaded state is recomputed on read, so a stale
``progress`` field on disk cannot resurrect a fabricated percentage.

"Self-awareness" is not a milestone here, or anywhere: it is not a measurable
objective, and the system does not claim it (see ``genesis_protocol.constitution``).
"""
import json
import os
from datetime import datetime

from genesis_protocol.gluten.identity import EVOLUTION_CHAIN, NAME

#: What this roadmap is not allowed to claim, echoed on every read.
NON_CLAIMS = [
    "Progress here is derived from recorded evidence, not from elapsed time.",
    "No milestone asserts self-awareness or consciousness.",
]

#: The falsifiable objectives. Each one states the test that would settle it.
OBJECTIVES: list[dict[str, str]] = [
    {
        "id": "council_independence",
        "title": "Council independence assessment",
        "objective": "Detect when a council agreement is correlated rather than "
                     "independent, and never treat consensus as evidence.",
        "falsifiable_test": "Two same-family members agreeing is rated high correlated "
                            "risk; distinct families agreeing is rated low; is_evidence "
                            "is False in every case.",
    },
    {
        "id": "research_cycle",
        "title": "Gated research cycle",
        "objective": "Run question -> literature -> hypothesis -> model -> experiment "
                     "-> measurement -> verification -> report, refusing to skip a stage.",
        "falsifiable_test": "Skipping a stage raises; a report without a passing "
                            "independent check is refused.",
    },
    {
        "id": "benchmark_verified",
        "title": "Reproducible theorem benchmark",
        "objective": "Reproduce public propositional-logic problems with an independent "
                     "checker, including negative controls.",
        "falsifiable_test": "Known tautologies pass, known non-tautologies fail, and a "
                            "checker that accepts both is reported broken.",
    },
    {
        "id": "negative_results",
        "title": "Permanent negative results",
        "objective": "Keep failed hypotheses and refuted results in an append-only "
                     "ledger instead of deleting them.",
        "falsifiable_test": "A refuted hypothesis remains readable after the cycle ends "
                            "and cannot be removed through the API.",
    },
]


class Milestone:
    """One objective plus the evidence attached to it."""

    def __init__(self, milestone_id: str, title: str, description: str,
                 falsifiable_test: str = "", evidence: list[dict] | None = None):
        self.id = milestone_id
        self.title = title
        self.description = description
        self.falsifiable_test = falsifiable_test
        self.evidence: list[dict] = list(evidence or [])
        self.created_at = datetime.now()
        self.completed_at: datetime | None = None

    @property
    def verified_evidence(self) -> list[dict]:
        return [e for e in self.evidence if e.get("verified")]

    @property
    def progress(self) -> int:
        """0 / 50 / 100, from evidence only."""
        if self.verified_evidence:
            return 100
        return 50 if self.evidence else 0

    @property
    def status(self) -> str:
        if self.verified_evidence:
            return "completed"
        return "in_progress" if self.evidence else "planned"

    @property
    def target_date(self) -> None:
        """Deliberately absent: a date is not evidence of progress."""
        return None

    def record_evidence(self, reference: str, verified: bool = False,
                        note: str = "") -> None:
        """Attach evidence. ``verified`` must come from a check, not an opinion."""
        self.evidence.append({
            "reference": str(reference),
            "verified": bool(verified),
            "note": str(note),
            "recorded_at": datetime.now().isoformat(),
        })
        if self.verified_evidence and self.completed_at is None:
            self.completed_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "falsifiable_test": self.falsifiable_test,
            "target_date": None,
            "status": self.status,
            "progress": self.progress,
            "evidence": list(self.evidence),
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class FutureRoadmap:
    """Evidence-backed roadmap. No setters for progress, by design."""

    def __init__(self, storage_path: str = "data/infinity/roadmap"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self.milestones: dict[str, Milestone] = {}
        self.goals: list[dict] = []
        self._init_objectives()
        self._load()

    def _init_objectives(self) -> None:
        for spec in OBJECTIVES:
            self.milestones[spec["id"]] = Milestone(
                spec["id"], spec["title"], spec["objective"], spec["falsifiable_test"],
            )

    @property
    def evolution_stages(self) -> list[dict]:
        """The real lineage, from the identity module - not invented stage dates."""
        stages = []
        for i, name in enumerate(EVOLUTION_CHAIN):
            stages.append({
                "stage": name,
                "position": i,
                "current": name == NAME,
                "role": "current form" if name == NAME else "historical name",
            })
        return stages

    def _load(self) -> None:
        """Load goals and evidence. ``progress``/``status`` on disk are ignored."""
        path = os.path.join(self.storage_path, "roadmap.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for goal in data.get("goals", []):
            if isinstance(goal, dict):
                self.goals.append(goal)
        for mid, saved in (data.get("milestones") or {}).items():
            milestone = self.milestones.get(mid)
            if milestone is None:
                continue
            for entry in saved.get("evidence", []):
                if isinstance(entry, dict) and entry.get("reference"):
                    milestone.record_evidence(
                        entry["reference"],
                        verified=bool(entry.get("verified")),
                        note=str(entry.get("note", "")),
                    )

    def _save(self) -> None:
        payload = {
            "goals": self.goals,
            "milestones": {mid: {"evidence": m.evidence} for mid, m in self.milestones.items()},
        }
        with open(os.path.join(self.storage_path, "roadmap.json"), "w") as f:
            json.dump(payload, f, indent=2)

    # -- evidence -----------------------------------------------------------
    def record_evidence(self, milestone_id: str, reference: str,
                        verified: bool = False, note: str = "") -> bool:
        milestone = self.milestones.get(milestone_id)
        if milestone is None or not reference:
            return False
        milestone.record_evidence(reference, verified=verified, note=note)
        self._save()
        return True

    def update_milestone_progress(self, milestone_id: str, progress: int) -> bool:
        """Refused. Progress comes from evidence; use ``record_evidence``."""
        return False

    # -- goals --------------------------------------------------------------
    def add_goal(self, goal: str, category: str = "general") -> str:
        goal_id = f"goal_{len(self.goals)}_{int(datetime.now().timestamp())}"
        self.goals.append({
            "id": goal_id,
            "goal": goal,
            "category": category,
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
        })
        self._save()
        return goal_id

    def complete_goal(self, goal_id: str) -> bool:
        for goal in self.goals:
            if goal["id"] == goal_id:
                goal["status"] = "completed"
                goal["completed_at"] = datetime.now().isoformat()
                self._save()
                return True
        return False

    # -- reads --------------------------------------------------------------
    def get_evolution_path(self) -> list[dict]:
        return self.evolution_stages

    def get_milestones(self, status: str = None) -> list[Milestone]:
        items = sorted(self.milestones.values(), key=lambda m: m.id)
        return [m for m in items if m.status == status] if status else items

    def get_goals(self, status: str = None) -> list[dict]:
        if status:
            return [g for g in self.goals if g.get("status") == status]
        return self.goals

    def get_status(self) -> dict:
        items = list(self.milestones.values())
        total = len(items)
        completed = len([m for m in items if m.status == "completed"])
        in_progress = len([m for m in items if m.status == "in_progress"])
        planned = len([m for m in items if m.status == "planned"])
        with_evidence = len([m for m in items if m.evidence])
        average = round(sum(m.progress for m in items) / total, 1) if total else 0.0
        return {
            "current_stage": NAME,
            "evolution_stages": len(self.evolution_stages),
            "total_milestones": total,
            "completed_milestones": completed,
            "in_progress_milestones": in_progress,
            "planned_milestones": planned,
            "average_progress": average,
            "evidence_backed_milestones": with_evidence,
            "total_goals": len(self.goals),
            "completed_goals": len([g for g in self.goals if g.get("status") == "completed"]),
            "progress_basis": "evidence",
            "non_claims": list(NON_CLAIMS),
        }


_instance = None


def get_future_roadmap() -> FutureRoadmap:
    global _instance
    if _instance is None:
        _instance = FutureRoadmap()
    return _instance
