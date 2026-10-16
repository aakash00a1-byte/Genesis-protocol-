"""Sandbox boundaries for tool execution.

Blocks unrestricted host access, credential access, arbitrary destructive
operations, hidden persistence, and unauthorized network access.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from genesis.exceptions import SandboxViolation

_DESTRUCTIVE = re.compile(
    r"(?i)\b(rm\s+-rf|mkfs|dd\s+if=|:\(\)|shutdown|reboot|format\s+[a-z]:|"
    r"drop\s+database|truncate\s+table|delete\s+from\s+\w+\s*(where\s+1=1)?)"
)
_CREDENTIAL_ACCESS = re.compile(
    r"(?i)(\.env|\.pypirc|\.npmrc|\.ssh/id_rsa|id_rsa\.pub|credentials\.json|"
    r"service-account|api[_-]?key\.txt|\.aws/credentials|\.netrc)"
)
_NETWORK = re.compile(r"(?i)\b(curl|wget|nc\s+-|ncat|telnet|ssh\s+[^@]+@)\b")
_URL = re.compile(r"https?://[^\s'\"]+")
_URL_EXEMPT_CATEGORIES = {"browser", "search"}


@dataclass
class SandboxPolicy:
    """Declarative sandbox rules for a tool call."""

    allow_paths: list[str] = field(default_factory=lambda: ["/workspace"])
    deny_paths: list[str] = field(
        default_factory=lambda: [
            "/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys",
            "/root", "/home", "/var", "/dev",
        ]
    )
    allow_network: bool = False
    allow_destructive: bool = False
    allow_credential_access: bool = False
    allow_persistence: bool = False  # hidden persistence blocked by default
    max_args_bytes: int = 1_000_000
    url_exempt_categories: set[str] = field(
        default_factory=lambda: set(_URL_EXEMPT_CATEGORIES)
    )


class Sandbox:
    """Validates tool arguments against the sandbox policy."""

    def __init__(self, policy: SandboxPolicy | None = None) -> None:
        self.policy = policy or SandboxPolicy()

    def check(
        self, tool_name: str, args: dict, *, category: str | None = None
    ) -> None:
        """Raise SandboxViolation if the request crosses a boundary."""
        self._check_size(args)
        joined = self._flatten(args)

        # Path checks
        for path in self._extract_paths(args):
            self._check_path(path)

        # Credential access
        if not self.policy.allow_credential_access and _CREDENTIAL_ACCESS.search(
            joined
        ):
            raise SandboxViolation(
                f"credential access blocked in tool {tool_name}"
            )

        # Destructive operations
        if not self.policy.allow_destructive and _DESTRUCTIVE.search(joined):
            raise SandboxViolation(
                f"destructive operation blocked in tool {tool_name}"
            )

        # Network access: command-style access is always blocked; raw URLs are
        # blocked unless the tool category is explicitly exempt (browser/search).
        if not self.policy.allow_network:
            if _NETWORK.search(joined):
                raise SandboxViolation(
                    f"unauthorized network access blocked in tool {tool_name}"
                )
            if category not in self.policy.url_exempt_categories and _URL.search(
                joined
            ):
                raise SandboxViolation(
                    f"unauthorized URL access blocked in tool {tool_name}"
                )

    def _check_size(self, args: dict) -> None:
        size = len(str(args).encode("utf-8", errors="ignore"))
        if size > self.policy.max_args_bytes:
            raise SandboxViolation("tool arguments exceed sandbox size limit")

    def _check_path(self, path: str) -> None:
        if not path:
            return
        resolved = self._resolve(path)
        allowed = [self._resolve(p) for p in self.policy.allow_paths]
        if not any(
            resolved == a or resolved.startswith(a.rstrip("/") + "/")
            for a in allowed
        ):
            raise SandboxViolation(f"path outside sandbox: {path}")
        for denied in self.policy.deny_paths:
            d = self._resolve(denied)
            if resolved == d or resolved.startswith(d.rstrip("/") + "/"):
                raise SandboxViolation(f"path in denied zone: {path}")

    @staticmethod
    def _resolve(path: str) -> str:
        """Fully resolve a path, following symlinks.

        `abspath` only normalizes `..` lexically, so a symlink placed inside
        the allowed root becomes a back door to a path outside it. `realpath`
        resolves the link, so the boundary is checked against the real target.
        """
        return os.path.realpath(os.path.expanduser(path))

    @staticmethod
    def _extract_paths(args: dict) -> list[str]:
        paths: list[str] = []
        for key, value in args.items():
            if key in {
                "path", "file", "directory", "dir", "cwd", "repo",
                "source", "destination", "dest", "target", "filename",
            }:
                if isinstance(value, str):
                    paths.append(value)
                elif isinstance(value, list):
                    paths.extend(v for v in value if isinstance(v, str))
        return paths

    @staticmethod
    def _flatten(args: dict) -> str:
        return " ".join(
            str(v) for v in args.values() if isinstance(v, (str, int, float))
        )