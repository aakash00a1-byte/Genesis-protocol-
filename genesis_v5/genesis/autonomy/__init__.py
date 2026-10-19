"""Bounded autonomous task-execution loop.

This package adds a *controller* on top of the existing Kernel — it does not
add a new execution path. Every tool call still travels the Tool Gateway
(policy -> permission -> sandbox -> execute -> audit), every agent still comes
from the existing 8-agent registry, and the Kernel remains the authority.

The loop is:
  - off by default (`AutonomyConfig.enabled`),
  - bounded in iterations, retries, and wall-clock time,
  - checkpointed to disk so an interrupted run can resume,
  - gated by an explicit forbidden-action guard, and
  - forbidden from pushing, deploying, publishing, or touching credentials.

See `genesis/autonomy/loop.py` for the runnable loop and
`tests/integration/test_autonomy.py` for the reproducible end-to-end proof.
"""
from __future__ import annotations

from .acceptance import AcceptanceGate, AcceptanceReport
from .guard import ForbiddenActionError, GuardDecision, TaskGuard
from .loop import AutonomousLoop, AutonomyRunResult, RunStatus
from .state import Checkpoint, TaskState, TaskStatus, TaskStore

__all__ = [
    "AutonomousLoop",
    "AutonomyRunResult",
    "RunStatus",
    "TaskState",
    "TaskStore",
    "TaskStatus",
    "Checkpoint",
    "TaskGuard",
    "GuardDecision",
    "ForbiddenActionError",
    "AcceptanceGate",
    "AcceptanceReport",
]
