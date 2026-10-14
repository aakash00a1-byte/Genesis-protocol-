"""Tool registry and tool specification.

A tool spec declares identity, category, JSON schema, required permission,
risk level, execution policy (which agents may invoke it), and timeout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from genesis.core import RiskLevel
from genesis.security.permissions import Permission


class ToolCategory(str, Enum):
    BROWSER = "browser"
    SEARCH = "search"
    FILES = "files"
    GIT = "git"
    PYTHON = "python"
    TERMINAL = "terminal"
    DOCKER = "docker"
    APIS = "apis"


@dataclass
class ToolContext:
    """What the gateway provides to a tool implementation."""

    actor: str
    role: str
    sandbox: Any  # genesis.tools.sandbox.Sandbox
    cwd: str = "/workspace"
    environment: dict[str, str] = field(default_factory=dict)
    audit: Any = None  # AuditLogger


ToolImpl = Callable[[ToolContext, dict[str, Any]], Any]


@dataclass
class ToolSpec:
    name: str
    category: ToolCategory
    description: str
    schema: dict[str, Any]  # JSON-schema-ish dict with title/properties/required
    permission: Permission
    risk_level: RiskLevel = RiskLevel.LOW
    timeout_seconds: float = 30.0
    invocation_policy: str = "kernel_only"  # kernel_only | role_gated
    offline: bool = True
    enabled: bool = True
    handler: ToolImpl | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "schema": self.schema,
            "permission": self.permission.value,
            "risk_level": self.risk_level.value,
            "timeout_seconds": self.timeout_seconds,
            "invocation_policy": self.invocation_policy,
            "offline": self.offline,
            "enabled": self.enabled,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolImpl] = {}

    def register(self, spec: ToolSpec, handler: ToolImpl | None = None) -> None:
        if handler is not None:
            spec.handler = handler
        self._specs[spec.name] = spec
        if spec.handler is not None:
            self._handlers[spec.name] = spec.handler

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def has(self, name: str) -> bool:
        return name in self._specs

    def handler(self, name: str) -> ToolImpl | None:
        return self._handlers.get(name)

    def categories(self) -> list[str]:
        return sorted({s.category.value for s in self._specs.values()})

    def by_category(self, category: ToolCategory) -> list[ToolSpec]:
        return [s for s in self._specs.values() if s.category == category]

    def all(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def clear(self) -> None:
        self._specs.clear()
        self._handlers.clear()