"""Bounded autonomous task-execution loop.

The loop drives the *existing* Kernel; it never executes a tool itself and
never picks a tool directly. For each iteration it hands the task to
``Kernel.run`` — the same path a human request takes — and then verifies the
result independently. It stops on success, on a hard failure, or when a bound
is reached, and it always leaves a checkpoint on disk.

Bounds (all finite, from ``AutonomyConfig``):
  - ``max_iterations``   — total loop iterations
  - ``max_retries_per_step`` — retries after a failed iteration
  - ``max_wall_clock_seconds`` — hard wall-clock ceiling
  - ``step_timeout_seconds`` — per-iteration ceiling

Forbidden actions (push/deploy/publish/credentials/disable-security) and
prompt-injection markers are refused by ``TaskGuard`` before any work starts,
and unsafe tools are refused before the Kernel sees them.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.config.settings import AutonomyConfig
from genesis.core import MemoryScope, RiskLevel, ToolStatus
from genesis.kernel.kernel import KernelRequest
from genesis.tools.gateway import ToolRequest

from .acceptance import AcceptanceGate
from .guard import TaskGuard
from .state import TaskState, TaskStatus, TaskStore

logger = logging.getLogger(__name__)


class RunStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    LIMIT_REACHED = "limit_reached"
    TIMED_OUT = "timed_out"
    BLOCKED = "blocked"


@dataclass
class AutonomyRunResult:
    run_id: str
    status: RunStatus
    iterations: int
    attempts: int
    ok: bool
    result: Any = None
    errors: list[str] = field(default_factory=list)
    audit_ids: list[str] = field(default_factory=list)
    checkpoint_path: str = ""
    blocked_reason: str = ""
    elapsed_ms: int = 0
    recon: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "iterations": self.iterations,
            "attempts": self.attempts,
            "ok": self.ok,
            "result": self.result,
            "errors": list(self.errors),
            "audit_ids": list(self.audit_ids),
            "checkpoint_path": self.checkpoint_path,
            "blocked_reason": self.blocked_reason,
            "elapsed_ms": self.elapsed_ms,
            "recon": dict(self.recon),
        }


class AutonomousLoop:
    """A bounded controller around ``Kernel.run``.

    The loop is disabled unless ``AutonomyConfig.enabled`` is true. It is a
    thin orchestrator: the Kernel, agents, gateway, sandbox, and audit layers
    are all reused unchanged.
    """

    def __init__(
        self,
        kernel: Any,
        config: AutonomyConfig | None = None,
        *,
        guard: TaskGuard | None = None,
        store: TaskStore | None = None,
        acceptance: AcceptanceGate | None = None,
        changes: dict[str, str] | None = None,
        recon: list[ToolRequest] | None = None,
        sleep: Any = time.sleep,
        now: Any = time.monotonic,
    ) -> None:
        self.kernel = kernel
        self.config = config or AutonomyConfig()
        self.guard = guard or TaskGuard(
            refuse_on_injection=self.config.refuse_on_injection
        )
        self.store = store or TaskStore(self.config.checkpoint_dir)
        self.acceptance = acceptance
        # The proposed code changes a run wants accepted. When a gate is wired,
        # a run is only "succeeded" if the gate accepts these.
        self.changes = changes
        # Optional read-only reconnaissance, driven by the loop. Each request
        # still travels the full gate; the standing grant only removes a
        # per-call approval. Defaults to a small, fixed read-only set.
        self.recon = recon if recon is not None else self._default_recon()
        self._sleep = sleep
        self._now = now

    def _default_recon(self) -> list[ToolRequest]:
        """A minimal read-only reconnaissance set for the run's actor.

        These are only attempted when the standing grant lists the matching
        permission; otherwise the gate denies them and the run proceeds. They
        never mutate anything — writes and exec tools are never included.
        """
        return [
            ToolRequest(tool="file.list", args={}),
            ToolRequest(tool="git.status", args={}),
            ToolRequest(tool="git.log", args={}),
        ]

    # ------------------------------------------------------------------
    @property
    def max_risk(self) -> RiskLevel:
        try:
            return RiskLevel(self.config.max_risk)
        except ValueError:
            return RiskLevel.MEDIUM

    def _run_once(
        self, state: TaskState, *, timeout_seconds: float
    ) -> Any:
        """One iteration: hand the task to the Kernel, under a time ceiling.

        Runs the Kernel call on a daemon thread so a hung call cannot pin the
        loop forever. This bounds the *loop*; the Kernel's own tool timeouts
        bound individual tools.
        """
        import threading

        box: dict[str, Any] = {}

        def target() -> None:
            try:
                box["response"] = self.kernel.run(
                    KernelRequest(
                        task=state.task,
                        actor=state.actor,
                        role=state.role,
                        scope=MemoryScope.TASK,
                        metadata={"max_risk": self.max_risk, "autonomy": True},
                    )
                )
            except Exception as exc:  # noqa: BLE001
                box["error"] = exc

        worker = threading.Thread(target=target, daemon=True)
        worker.start()
        worker.join(timeout=timeout_seconds)
        if worker.is_alive():
            raise TimeoutError(
                f"iteration exceeded step timeout ({timeout_seconds:.1f}s)"
            )
        if "error" in box:
            raise box["error"]
        return box.get("response")

    # ------------------------------------------------------------------
    def _recon_once(self, state: TaskState) -> dict[str, Any]:
        """Run the loop's read-only recon through the full authority gate.

        Every request is executed via ``Kernel.execute_tool`` — policy,
        permission, sandbox, and audit all still apply. A request is only
        auto-approved when the gateway's standing grant covers it (matching
        actor + listed permission + LOW ceiling); otherwise it is denied and
        recorded. Nothing here is executed directly, and nothing here writes.
        """
        outcomes: dict[str, Any] = {}
        for base in self.recon:
            request = ToolRequest(
                tool=base.tool,
                args=dict(base.args),
                actor=state.actor,
                role=state.role,
                cwd=base.cwd,
            )
            try:
                result = self.kernel.execute_tool(request)
                status = getattr(result, "status", None)
                status_value = (
                    status.value if isinstance(status, ToolStatus) else str(status)
                )
                outcomes[base.tool] = {
                    "status": status_value,
                    "granted": status is ToolStatus.SUCCESS,
                }
            except Exception as exc:  # noqa: BLE001
                outcomes[base.tool] = {
                    "status": "error",
                    "granted": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
        return outcomes

    # ------------------------------------------------------------------
    def run(self, task: str, *, actor: str = "autonomy", role: str = "coder") -> AutonomyRunResult:
        """Run one bounded autonomous task, or refuse it safely."""
        start = self._now()
        state = TaskState(task=task, actor=actor, role=role)

        if not self.config.enabled:
            state.status = TaskStatus.BLOCKED
            state.blocked_reason = "autonomy disabled (AutonomyConfig.enabled=False)"
            path = self.store.save(state)
            return AutonomyRunResult(
                run_id=state.run_id,
                status=RunStatus.BLOCKED,
                iterations=0,
                attempts=0,
                ok=False,
                blocked_reason=state.blocked_reason,
                checkpoint_path=path,
            )

        # Guard runs before anything else: a forbidden/injected task never
        # reaches an agent or the Kernel.
        decision = self.guard.scan_text(task)
        if not decision.allowed:
            state.status = TaskStatus.BLOCKED
            state.blocked_reason = decision.reason
            path = self.store.save(state)
            self.kernel.audit.record(
                event_type="autonomy.blocked",
                actor=actor,
                action="autonomy.run",
                status="denied",
                risk_level="high",
                details={"run_id": state.run_id, "reason": decision.reason},
            )
            return AutonomyRunResult(
                run_id=state.run_id,
                status=RunStatus.BLOCKED,
                iterations=0,
                attempts=0,
                ok=False,
                blocked_reason=decision.reason,
                checkpoint_path=path,
            )

        return self._loop(state, start=start)

    # ------------------------------------------------------------------
    def resume(self, run_id: str) -> AutonomyRunResult:
        """Continue a previously interrupted run from its checkpoint."""
        state = self.store.load(run_id)
        if state is None:
            raise FileNotFoundError(f"no checkpoint for run {run_id!r}")
        if not state.resumable:
            # Already finished (succeeded or blocked): report the stored
            # terminal status instead of silently re-running it.
            status = (
                RunStatus.SUCCEEDED
                if state.status is TaskStatus.SUCCEEDED
                else RunStatus.BLOCKED
            )
            return self._result_from_state(state, status=status)
        state.status = TaskStatus.RUNNING
        self.kernel.audit.record(
            event_type="autonomy.resume",
            actor=state.actor,
            action="autonomy.resume",
            status="success",
            details={"run_id": state.run_id, "from_iteration": state.iteration},
        )
        return self._loop(state, start=self._now())

    # ------------------------------------------------------------------
    def _loop(self, state: TaskState, *, start: float) -> AutonomyRunResult:
        deadline = start + float(self.config.max_wall_clock_seconds)
        max_iterations = max(1, int(self.config.max_iterations))
        max_retries = max(0, int(self.config.max_retries_per_step))
        step_timeout = max(0.001, float(self.config.step_timeout_seconds))

        self.kernel.audit.record(
            event_type="autonomy.start",
            actor=state.actor,
            action="autonomy.run",
            status="success",
            details={
                "run_id": state.run_id,
                "task": state.task[:200],
                "max_iterations": max_iterations,
            },
        )

        # Read-only reconnaissance, driven by the loop through the full gate.
        # Bounded (a fixed, small set) and side-effect free. A denied recon
        # never fails the run; it is recorded and the run proceeds.
        recon = self._recon_once(state)
        state.recon = recon
        if recon:
            self.kernel.audit.record(
                event_type="autonomy.recon",
                actor=state.actor,
                action="autonomy.recon",
                status="success",
                details={"run_id": state.run_id, "outcomes": recon},
            )

        retries_used = 0
        status = RunStatus.FAILED
        while state.iteration < max_iterations:
            if self._now() >= deadline:
                status = RunStatus.TIMED_OUT
                state.add_checkpoint(status=TaskStatus.INTERRUPTED)
                state.errors.append("wall-clock limit reached")
                break

            state.iteration += 1
            state.attempts += 1
            state.add_checkpoint(status=TaskStatus.RUNNING)

            try:
                response = self._run_once(state, timeout_seconds=step_timeout)
            except TimeoutError as exc:
                state.errors.append(str(exc))
                self.kernel.audit.record(
                    event_type="autonomy.iteration_timeout",
                    actor=state.actor,
                    action="autonomy.iteration",
                    status="failure",
                    details={"run_id": state.run_id, "iteration": state.iteration},
                )
                if self._now() >= deadline:
                    status = RunStatus.TIMED_OUT
                    state.add_checkpoint(status=TaskStatus.INTERRUPTED)
                    break
                if retries_used < max_retries:
                    retries_used += 1
                    continue
                status = RunStatus.FAILED
                state.add_checkpoint(status=TaskStatus.FAILED)
                break
            except Exception as exc:  # noqa: BLE001
                state.errors.append(f"{type(exc).__name__}: {exc}")
                if retries_used < max_retries:
                    retries_used += 1
                    self._sleep(self._backoff(retries_used))
                    continue
                status = RunStatus.FAILED
                state.add_checkpoint(status=TaskStatus.FAILED)
                break

            ok = bool(getattr(response, "ok", False))
            result = getattr(response, "result", None)
            audit_ids = list(getattr(response, "audit_ids", []) or [])
            state.audit_ids.extend(audit_ids)

            if ok and result is not None:
                # Acceptance gate: a code change is not accepted until tests
                # and security checks pass. No gate wired → unchanged behavior.
                if self.acceptance is not None:
                    report = self.acceptance.evaluate(self.changes or {})
                    if not report.accepted:
                        reason = "; ".join(report.reasons) or "acceptance failed"
                        state.errors.append(reason)
                        self.kernel.audit.record(
                            event_type="autonomy.change_rejected",
                            actor=state.actor,
                            action="autonomy.accept",
                            status="denied",
                            risk_level="medium",
                            details={
                                "run_id": state.run_id,
                                "reasons": report.reasons,
                                "secret_findings": report.secret_findings,
                            },
                        )
                        if retries_used < max_retries:
                            retries_used += 1
                            self._sleep(self._backoff(retries_used))
                            continue
                        status = RunStatus.FAILED
                        state.add_checkpoint(status=TaskStatus.FAILED)
                        break
                status = RunStatus.SUCCEEDED
                state.result = result
                state.add_checkpoint(
                    status=TaskStatus.SUCCEEDED, result=result
                )
                self.kernel.audit.record(
                    event_type="autonomy.succeeded",
                    actor=state.actor,
                    action="autonomy.iteration",
                    status="success",
                    details={
                        "run_id": state.run_id,
                        "iteration": state.iteration,
                    },
                )
                break

            errors = list(getattr(response, "errors", []) or [])
            state.errors.extend(errors or ["iteration produced no result"])
            if retries_used < max_retries:
                retries_used += 1
                self._sleep(self._backoff(retries_used))
                continue
            status = RunStatus.FAILED
            state.add_checkpoint(status=TaskStatus.FAILED)
            break
        else:
            status = RunStatus.LIMIT_REACHED
            state.add_checkpoint(status=TaskStatus.LIMIT_REACHED)

        path = self.store.save(state)
        return self._result_from_state(state, status=status, path=path)

    def _backoff(self, attempt: int) -> float:
        base = 0.05
        return base * (2 ** max(0, attempt - 1))

    def _result_from_state(
        self,
        state: TaskState,
        *,
        status: RunStatus,
        path: str = "",
    ) -> AutonomyRunResult:
        return AutonomyRunResult(
            run_id=state.run_id,
            status=status,
            iterations=state.iteration,
            attempts=state.attempts,
            ok=status is RunStatus.SUCCEEDED,
            result=state.result,
            errors=list(state.errors),
            audit_ids=list(state.audit_ids),
            checkpoint_path=path or self.store.path_for(state.run_id),
            blocked_reason=state.blocked_reason,
            elapsed_ms=max(0, state.updated_ms - state.started_ms),
            recon=dict(state.recon),
        )
