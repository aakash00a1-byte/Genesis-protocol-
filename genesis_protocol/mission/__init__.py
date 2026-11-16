"""Mission-level autonomy (V7 P10).

Genesis can carry out a *mission* - a goal too large for one step - while every
guard rail stays in place:

* ``planner``      - plan a goal into a validated task DAG (side-effect free);
* ``delegation``   - hand a task to a *verified* identity with a narrowed grant,
                     reusing the canonical identity registry;
* ``resources``    - check each step against a budget, reusing the canonical
                     survival layer; unreadable readings fail closed;
* ``tracking``     - progress and replanning (a failed task is replaced, the
                     mission is re-versioned, the change is recorded);
* ``verification`` - a task is done only when its result passes declarative
                     checks; unknown checks and missing fields fail closed;
* ``manager``      - the loop, which runs only with an explicit owner approval
                     and a runner the owner supplies.

Rules this package holds to:

* **Plan freely, run on approval.** Planning has no side effects; execution
  requires ``owner_approved=True`` and a caller-supplied runner.
* **Verify before done.** A task is marked done only after verification passes.
* **Delegate down, never up.** A delegate's tools must be a subset of the
  delegator's grant.
* **Fail closed.** Unreadable resources, unknown checks and unverifiable results
  are refusals, not passes.
* **Auditable.** Every transition is written to the canonical
  ``SecurityEventLog`` under source ``mission``.
* **No privileged work.** The manager never merges, deploys, or changes secrets.
"""
from genesis_protocol.mission.delegation import (
    Delegation,
    DelegationManager,
    DelegationRefused,
)
from genesis_protocol.mission.manager import (
    DEFAULT_MAX_STEPS,
    MissionManager,
    MissionRefused,
)
from genesis_protocol.mission.planner import (
    MAX_TASKS,
    STATUS_BLOCKED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_READY,
    STATUS_RUNNING,
    STATUS_SKIPPED,
    Mission,
    MissionTask,
    decompose,
    plan,
)
from genesis_protocol.mission.resources import (
    ResourceBudget,
    ResourceDecision,
    ResourceGovernor,
    ResourceSnapshot,
)
from genesis_protocol.mission.tracking import Progress, Replanner, progress
from genesis_protocol.mission.verification import (
    KNOWN_OPS,
    ResultVerifier,
    VerificationOutcome,
)

__all__ = [
    "MissionManager",
    "MissionRefused",
    "DEFAULT_MAX_STEPS",
    "Mission",
    "MissionTask",
    "plan",
    "decompose",
    "MAX_TASKS",
    "STATUS_PENDING",
    "STATUS_READY",
    "STATUS_RUNNING",
    "STATUS_DONE",
    "STATUS_FAILED",
    "STATUS_BLOCKED",
    "STATUS_SKIPPED",
    "DelegationManager",
    "Delegation",
    "DelegationRefused",
    "ResourceGovernor",
    "ResourceBudget",
    "ResourceDecision",
    "ResourceSnapshot",
    "Replanner",
    "Progress",
    "progress",
    "ResultVerifier",
    "VerificationOutcome",
    "KNOWN_OPS",
]
