"""Agent Registry."""
from __future__ import annotations

from typing import Callable

from .base import Agent

AgentBuilder = Callable[[], Agent]


class AgentRegistry:
    def __init__(self) -> None:
        self._builders: dict[str, AgentBuilder] = {}
        self._instances: dict[str, Agent] = {}

    def register(self, name: str, builder: AgentBuilder) -> None:
        self._builders[name] = builder

    def names(self) -> list[str]:
        return sorted(self._builders)

    def has(self, name: str) -> bool:
        return name in self._builders

    def create(self, name: str) -> Agent:
        if name not in self._builders:
            raise KeyError(f"unknown agent {name!r}")
        agent = self._builders[name]()
        self._instances[name] = agent
        return agent

    def get(self, name: str) -> Agent | None:
        if name in self._instances:
            return self._instances[name]
        if name in self._builders:
            return self.create(name)
        return None

    def all_instances(self) -> list[Agent]:
        return list(self._instances.values())

    def reset_all(self) -> None:
        for agent in self._instances.values():
            agent.reset()