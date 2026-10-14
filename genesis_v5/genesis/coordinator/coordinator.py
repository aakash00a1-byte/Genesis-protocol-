"""AgentCoordinator: executes a Plan on the Agent Registry.

Dependency-aware execution runs independent levels in parallel (bounded by a
worker count), applies bounded retries with backoff, aggregates results, and
rescues failures at the coordinator level without ever marking agent output
as automatically correct.

The Kernel remains the authority: the coordinator is wired into the Kernel
and returns results to it for reflection/QA.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from genesis.agents.base import Agent, AgentResult, AgentState, AgentTask
from genesis.agents.registry import AgentRegistry
from genesis.exceptions import RetryLimitExceeded
from genesis.planning.planner import Plan, PlanStep, Planner
from genesis.providers.base import ModelCapability

from .aggregator import AggregatedResult, aggregate

logger = logging.getLogger(__name__)


@dataclass
class CoordinatorConfig:
    max_retries: int = 3
    retry_backoff_base: float = 0.05
    max_parallel: int = 4
    retry_on_failure: bool = True


class AgentCoordinator:
    def __init__(
        self,
        registry: AgentRegistry,
        planner: Planner,
        config: CoordinatorConfig | None = None,
    ) -> None:
        self.registry = registry
        self.planner = planner
        self.config = config or CoordinatorConfig()
        self._state: dict[str, Any] = {}

    # ------------------------------------------------------------------
    def run_task(
        self,
        *,
        task: str,
        capability: ModelCapability = ModelCapability.CODE,
        actor: str = "kernel",
        role: str = "coder",
        max_retries: int | None = None,
    ) -> Any:
        """Plan and execute a task, returning the aggregated summary.

        Returns the aggregated summary text (string) so the Kernel can treat
        it uniformly with direct model completions.
        """
        plan = self.planner.plan(task)
        plan_result = self.execute_plan(
            plan,
            actor=actor,
            role=role,
            max_retries=max_retries or self.config.max_retries,
        )
        self._state[task] = {"plan": plan, "result": plan_result}
        return plan_result.summary

    def execute_plan(
        self,
        plan: Plan,
        *,
        actor: str = "kernel",
        role: str = "coder",
        max_retries: int | None = None,
    ) -> AggregatedResult:
        """Execute all plan steps respecting the dependency graph."""
        retries = max_retries or self.config.max_retries
        plan.graph.validate()  # raises CircularDependencyError
        levels = plan.graph.levels()

        step_map = {s.id: s for s in plan.steps}
        outputs: dict[str, AgentResult] = {}
        aggregated = AggregatedResult()

        for level in levels:
            level_results: dict[str, AgentResult] = {}
            step_items = [(sid, step_map[sid]) for sid in level]
            # Parallel-safe: each step in a level is independent. Run with a
            # bounded worker pool to avoid unbounded concurrency.
            results_by_id = self._run_level_parallel(
                step_items, actor=actor, role=role, max_retries=retries
            )
            for step_id, result in results_by_id.items():
                level_results[step_id] = result
                outputs[step_id] = result
                aggregated.add(result)
            self._merge_into_plan_state(plan, level_results)

        aggregated.finalize()
        return aggregated

    # ------------------------------------------------------------------
    def _run_level_parallel(
        self,
        step_items: list[tuple[str, PlanStep]],
        *,
        actor: str,
        role: str,
        max_retries: int,
    ) -> dict[str, AgentResult]:
        """Run independent steps concurrently, bounded by max_parallel."""
        if len(step_items) <= 1:
            step_id, step = step_items[0]
            return {
                step_id: self._run_step(step, actor=actor, role=role,
                                        max_retries=max_retries)
            }
        results: dict[str, AgentResult] = {}
        errors: dict[str, BaseException] = {}
        lock = threading.Lock()

        def worker(step_id: str, step: PlanStep) -> None:
            try:
                result = self._run_step(
                    step, actor=actor, role=role, max_retries=max_retries
                )
                with lock:
                    results[step_id] = result
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors[step_id] = exc

        batch_size = max(1, self.config.max_parallel)
        for start in range(0, len(step_items), batch_size):
            batch = step_items[start : start + batch_size]
            threads = [
                threading.Thread(
                    target=worker, args=(sid, step), daemon=True
                )
                for sid, step in batch
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        if errors:
            # Surface the first error deterministically (list order).
            first = min(errors, key=lambda sid: [s for s, _ in step_items].index(sid))
            raise errors[first]
        return results

    def _run_step(
        self,
        step: PlanStep,
        *,
        actor: str,
        role: str,
        max_retries: int,
    ) -> AgentResult:
        attempt = 0
        last_error = ""
        while attempt < max_retries:
            attempt += 1
            try:
                agent = self.registry.get(step.agent)
                if agent is None:
                    raise RetryLimitExceeded(f"unknown agent {step.agent!r}")
                task = AgentTask(
                    agent=step.agent,
                    instruction=step.instruction,
                    context={"task": self._current_task, "plan": step.id},
                )
                result = agent.run(task)
                if result.ok:
                    result.attempts = attempt
                    return result
                last_error = result.error or "agent returned failure"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
            if self.config.retry_on_failure:
                time.sleep(self._backoff(attempt))
        raise RetryLimitExceeded(
            f"agent {step.agent!r} failed after {max_retries} attempts: {last_error}"
        )

    # ------------------------------------------------------------------
    def _backoff(self, attempt: int) -> float:
        base = self.config.retry_backoff_base
        return min(base * (2 ** (attempt - 1)), 1.0)

    def _merge_into_plan_state(self, plan: Plan, results: dict[str, AgentResult]) -> None:
        for step in plan.steps:
            if step.id in results:
                self._state.setdefault("steps", {})[step.id] = results[
                    step.id
                ].to_dict()

    @property
    def _current_task(self) -> str:
        # Seed the context with the original task when available.
        return str(self._state.get("last_task", ""))

    def set_current_task(self, task: str) -> None:
        self._state["last_task"] = task

    def state_snapshot(self) -> dict[str, Any]:
        return dict(self._state)