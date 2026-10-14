"""Result aggregation for multi-agent execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from genesis.agents.base import AgentResult, AgentState


@dataclass
class AggregatedResult:
    """Combined outcome of a plan."""

    ok: bool = True
    steps: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[Any] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0

    def add(self, result: AgentResult) -> None:
        self.steps.append(result.to_dict())
        self.attempted += 1
        if result.ok:
            self.succeeded += 1
            self.outputs.append(result.output)
        else:
            self.failed += 1
            self.errors.append(f"{result.agent}: {result.error}")

    @property
    def summary(self) -> str:
        if not self.steps:
            return "no steps executed"
        if self.ok:
            return " ".join(str(o) for o in self.outputs if o is not None)
        return "; ".join(self.errors)

    def finalize(self) -> "AggregatedResult":
        self.ok = self.failed == 0
        return self


def aggregate(results: list[AgentResult]) -> AggregatedResult:
    aggregated = AggregatedResult()
    for result in results:
        aggregated.add(result)
    return aggregated.finalize()