"""Permissions, roles, and the policy engine.

Zero-trust: nothing is implicitly permitted. Every tool call, memory access,
and agent action is checked against an explicit grant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from genesis.core import RiskLevel


class Permission(str, Enum):
    """Granular capabilities. Tool access is derived from these."""

    # Tools
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_LIST = "file.list"
    GIT_READ = "git.read"
    GIT_WRITE = "git.write"
    PYTHON_EXEC = "python.exec"
    TERMINAL_EXEC = "terminal.exec"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_CLICK = "browser.click"
    BROWSER_TYPE = "browser.type"
    SEARCH_WEB = "search.web"
    DOCKER_EXEC = "docker.exec"
    API_CALL = "api.call"

    # Memory
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    MEMORY_SEARCH = "memory.search"

    # Agent coordination
    AGENT_CREATE = "agent.create"
    AGENT_RUN = "agent.run"
    AGENT_DELEGATE = "agent.delegate"

    # Admin
    AUDIT_READ = "audit.read"
    CONFIG_READ = "config.read"
    CONFIG_WRITE = "config.write"


@dataclass(frozen=True)
class PermissionSet:
    permissions: frozenset[Permission] = field(default_factory=frozenset)

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions

    def allows_any(self, permissions: Iterable[Permission]) -> bool:
        return any(p in self.permissions for p in permissions)

    def union(self, other: "PermissionSet") -> "PermissionSet":
        return PermissionSet(self.permissions | other.permissions)

    def to_list(self) -> list[str]:
        return sorted(p.value for p in self.permissions)


@dataclass(frozen=True)
class Role:
    name: str
    permissions: PermissionSet

    def can(self, permission: Permission) -> bool:
        return self.permissions.allows(permission)


class RoleCatalog:
    """Built-in roles. Zero-trust default role grants nothing."""

    NONE = Role("none", PermissionSet())
    MEMORY = Role(
        "memory",
        PermissionSet(frozenset([
            Permission.MEMORY_READ,
            Permission.MEMORY_WRITE,
            Permission.MEMORY_SEARCH,
        ])),
    )
    RESEARCHER = Role(
        "researcher",
        PermissionSet(frozenset([
            Permission.SEARCH_WEB,
            Permission.BROWSER_NAVIGATE,
            Permission.FILE_READ,
            Permission.FILE_LIST,
            Permission.MEMORY_READ,
            Permission.MEMORY_SEARCH,
        ])),
    )
    CODER = Role(
        "coder",
        PermissionSet(frozenset([
            Permission.FILE_READ,
            Permission.FILE_WRITE,
            Permission.FILE_LIST,
            Permission.GIT_READ,
            Permission.GIT_WRITE,
            Permission.PYTHON_EXEC,
            Permission.MEMORY_READ,
            Permission.MEMORY_WRITE,
        ])),
    )
    QA = Role(
        "qa",
        PermissionSet(frozenset([
            Permission.FILE_READ,
            Permission.FILE_LIST,
            Permission.PYTHON_EXEC,
            Permission.MEMORY_READ,
            Permission.MEMORY_SEARCH,
            Permission.TERMINAL_EXEC,
        ])),
    )
    SECURITY = Role(
        "security",
        PermissionSet(frozenset([
            Permission.FILE_READ,
            Permission.FILE_LIST,
            Permission.AUDIT_READ,
            Permission.MEMORY_READ,
            Permission.CONFIG_READ,
        ])),
    )
    OPERATOR = Role(
        "operator",
        PermissionSet(frozenset([
            Permission.TERMINAL_EXEC,
            Permission.DOCKER_EXEC,
            Permission.API_CALL,
            Permission.CONFIG_READ,
        ])),
    )
    ADMIN = Role(
        "admin",
        PermissionSet(frozenset(p for p in Permission)),
    )

    ALL = {
        r.name: r
        for r in [
            NONE, MEMORY, RESEARCHER, CODER, QA, SECURITY, OPERATOR, ADMIN,
        ]
    }

    @classmethod
    def get(cls, name: str) -> Role:
        return cls.ALL.get(name, cls.NONE)


class PolicyEngine:
    """Decides whether a request passes the permission gate."""

    def __init__(self, catalog: type[RoleCatalog] = RoleCatalog) -> None:
        self._catalog = catalog

    def check(
        self,
        *,
        permission: Permission,
        role_name: str | None = None,
        role: Role | None = None,
        max_risk: RiskLevel = RiskLevel.LOW,
        risk: RiskLevel = RiskLevel.LOW,
        allowed: bool = True,
    ) -> bool:
        """Gate decision.

        An explicit `allowed=False` always denies. Otherwise the role must
        hold the permission AND the risk must not exceed max_risk.
        """
        if not allowed:
            return False
        if risk.rank() > max_risk.rank():
            return False
        effective_role = role or (
            self._catalog.get(role_name) if role_name else self._catalog.NONE
        )
        return effective_role.can(permission)

    def allowed_tools(self, role_name: str) -> list[str]:
        role = self._catalog.get(role_name)
        tool_map = {
            Permission.FILE_READ: "files",
            Permission.FILE_WRITE: "files",
            Permission.FILE_LIST: "files",
            Permission.GIT_READ: "git",
            Permission.GIT_WRITE: "git",
            Permission.PYTHON_EXEC: "python",
            Permission.TERMINAL_EXEC: "terminal",
            Permission.BROWSER_NAVIGATE: "browser",
            Permission.SEARCH_WEB: "search",
            Permission.DOCKER_EXEC: "docker",
            Permission.API_CALL: "apis",
        }
        return sorted({t for p, t in tool_map.items() if role.can(p)})

    def has_role(self, role_name: str) -> bool:
        return role_name in self._catalog.ALL

    def roles(self) -> list[str]:
        return list(self._catalog.ALL)

    def allows_role(self, role_name: str, permission: Permission) -> bool:
        role = self._catalog.get(role_name)
        return role.can(permission)