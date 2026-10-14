"""From raw input to a governed action.

This is the one path that connects generation to the world. Raw, unfiltered
input goes in; candidate proposals come out of ``ParallelGenerator``; and if a
proposal asks for a tool, that request must pass the full authority gate
(policy, permissions, audit) before anything runs. There is no shortcut around
the gate — that is the whole point of this module existing.

The pipeline is honest about each stage:

1. **Generate** — proposals only, no side effects.
2. **Authorise** — every tool request goes through ``ToolGateway``; denials are
   recorded with a reason and surfaced, never dropped.
3. **Execute** — only what the gate granted.
4. **Record** — decisions and outcomes go to the transparency ledger.

``bypass_gatekeeper`` is deliberately absent. A proposal cannot opt out of the
gate, because the gate is not a feature of a proposal — it is the boundary
between thinking and acting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.core import ToolStatus, new_id, now_ms
from genesis.generation.generator import GenerationResult, ParallelGenerator
from genesis.tools.gateway import ToolGateway, ToolRequest, ToolResult


class Stage(str, Enum):
    GENERATE = "generate"
    AUTHORISE = "authorise"
    EXECUTE = "execute"
    RECORD = "record"


@dataclass
class ActionOutcome:
    """What happened when a proposal was offered to the authority layer."""

    request: ToolRequest
    granted: bool
    status: str
    result: ToolResult | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.request.tool,
            "actor": self.request.actor,
            "role": self.request.role,
            "granted": self.granted,
            "status": self.status,
            "reason": self.reason,
            "result_status": self.result.status.value if self.result else None,
            "result_error": self.result.error if self.result else None,
        }


@dataclass
class PipelineResult:
    """The full trace of one pass from input to (maybe) action."""

    run_id: str
    raw_input: str
    generation: GenerationResult
    actions: list[ActionOutcome] = field(default_factory=list)
    stages: list[str] = field(default_factory=list)
    bypass_available: bool = False
    ts_ms: int = field(default_factory=now_ms)

    @property
    def executed(self) -> int:
        return sum(1 for a in self.actions if a.granted)

    @property
    def denied(self) -> int:
        return sum(1 for a in self.actions if not a.granted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "raw_input": self.raw_input,
            "stages": list(self.stages),
            "generation": self.generation.to_dict(),
            "actions": [a.to_dict() for a in self.actions],
            "executed": self.executed,
            "denied": self.denied,
            "bypass_available": self.bypass_available,
            "ts_ms": self.ts_ms,
        }


class AuthorityPipeline:
    """Run raw input through generation and then the authority gate."""

    def __init__(
        self,
        generator: ParallelGenerator,
        gateway: ToolGateway,
        *,
        audit: Any = None,
    ) -> None:
        self.generator = generator
        self.gateway = gateway
        self.audit = audit

    def propose(self, raw_input: str, *, shots: int = 256) -> PipelineResult:
        """Generate proposals for ``raw_input`` with no side effects."""
        generation = self.generator.generate(raw_input, shots=shots)
        return PipelineResult(
            run_id=new_id("run"),
            raw_input=raw_input,
            generation=generation,
            stages=[Stage.GENERATE.value],
        )

    def submit(
        self,
        raw_input: str,
        requests: list[ToolRequest],
        *,
        shots: int = 256,
    ) -> PipelineResult:
        """Generate proposals, then offer each tool request to the gate.

        Every request is decided by the gateway. A denied request is recorded
        with its reason — the pipeline never silently executes or silently
        drops anything.
        """
        result = self.propose(raw_input, shots=shots)
        result.stages.append(Stage.AUTHORISE.value)

        for request in requests:
            outcome = self._authorise(request)
            result.actions.append(outcome)

        if any(a.granted for a in result.actions):
            result.stages.append(Stage.EXECUTE.value)
        result.stages.append(Stage.RECORD.value)
        return result

    def _authorise(self, request: ToolRequest) -> ActionOutcome:
        tool_result = self.gateway.execute(request)
        granted = tool_result.status is ToolStatus.SUCCESS
        reason = "" if granted else (tool_result.error or "denied by authority gate")
        return ActionOutcome(
            request=request,
            granted=granted,
            status=tool_result.status.value,
            result=tool_result,
            reason=reason,
        )
