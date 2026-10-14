"""Agent abstractions.

Agents are subordinate to the Kernel. They receive a task, execute within
their granted permissions and the sandbox, and return a structured AgentResult.
Agents never call tools directly — they request tool calls, and the Kernel
routes those requests through the Tool Gateway.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from genesis.core import new_id


class AgentState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass
class AgentResult:
    agent: str
    task_id: str = ""
    status: AgentState = AgentState.SUCCESS
    output: Any = None
    error: str = ""
    attempts: int = 1
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "attempts": self.attempts,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @property
    def ok(self) -> bool:
        return self.status == AgentState.SUCCESS


@dataclass
class AgentTask:
    """A subtask the Kernel hands to a single agent."""

    id: str = field(default_factory=lambda: new_id("task"))
    agent: str = "generic"
    instruction: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent": self.agent,
            "instruction": self.instruction,
            "dependencies": list(self.dependencies),
            "metadata": dict(self.metadata),
        }


ToolRequestFn = Callable[[str, dict[str, Any]], Any]


class Agent(ABC):
    """Base class for all Genesis agents."""

    name = "base"
    description = "Base agent."

    def __init__(self, tool_request: ToolRequestFn | None = None) -> None:
        self._tool_request = tool_request
        self.state = AgentState.IDLE
        self._metadata: dict[str, Any] = {}

    @abstractmethod
    def run(self, task: AgentTask) -> AgentResult:
        """Execute the subtask and return a structured result."""

    def request_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Ask the Kernel to execute a tool. Agents cannot execute directly."""
        if self._tool_request is None:
            raise PermissionError(
                "agent has no tool gateway; tool requests must go through Kernel"
            )
        return self._tool_request(name, args)

    def reset(self) -> None:
        self.state = AgentState.IDLE
        self._metadata.clear()


def base_agent_decorator(agent_cls: type) -> type:
    """No-op marker retained for future A/B instrumentation."""
    return agent_cls