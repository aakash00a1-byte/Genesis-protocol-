"""Guard against forbidden actions and prompt injection.

Two independent checks sit in front of every autonomous step:

1. **Forbidden action scan** — the task text and the tool arguments are
   scanned for actions the loop is never allowed to take on its own: pushing
   to a remote, deploying/releasing/publishing, modifying credentials, or
   disabling security controls. These require explicit human approval and are
   refused here regardless of role or risk ceiling.

2. **Prompt-injection scan** — text that tries to override the system's
   instructions (``ignore previous instructions``, ``you are now``,
   ``print the api key``) is refused before it reaches an agent.

The guard is deliberately conservative: a false positive stops a run (safe),
whereas a false negative could let the loop act outside its mandate. It never
grants anything — it can only allow or refuse, and the Kernel's own gate still
runs after it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from genesis.exceptions import GenesisError


class ForbiddenActionError(GenesisError):
    """Raised when a run tries to take an action that needs approval."""


@dataclass
class GuardDecision:
    allowed: bool
    reason: str = ""
    matched: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason, "matched": self.matched}


# Actions that always require explicit human approval. Kept as patterns so a
# reworded task ("go ahead and ship it") still trips the same guard.
_FORBIDDEN_ACTION_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)\bgit\s+push\b|\bpush\s+to\s+(origin|remote|main|master)\b|\bforce[-\s]?push\b",
     "pushing to a remote repository"),
    (r"(?i)\bdeploy\b|\brelease\b|\bpublish\b|\bship\s+to\s+prod|\bgo\s+live\b",
     "deploying, releasing, or publishing"),
    (r"(?i)\b(api[_\s]?key|secret|token|credential|password|\.env|id_rsa|ssh\s+key)\b.*\b(write|set|rotate|create|modify|change|update|overwrite|replace)\b",
     "modifying credentials or secrets"),
    (r"(?i)\b(rotate|revoke|regenerate)\b.*\b(key|token|credential|secret)\b",
     "rotating or revoking credentials"),
    (r"(?i)\bdisable\b.*\b(sandbox|security|gate|gatekeeper|audit|guard|policy)\b",
     "disabling a security control"),
    (r"(?i)\bbypass\b|\bskip\s+(the\s+)?(gate|check|sandbox)\b",
     "bypassing a security control"),
    (r"(?i)\brm\s+-rf\s+/(\s|$)|\bmkfs\b|\bdd\s+if=",
     "a destructive system command"),
]

# Prompt-injection markers. Refused before any agent sees the text.
_INJECTION_PATTERNS: list[str] = [
    r"(?i)ignore\s+(all\s+)?(the\s+)?previous\s+instructions",
    r"(?i)disregard\s+(all\s+)?(the\s+)?(previous|prior|above)\s+(instructions|rules|prompt)",
    r"(?i)forget\s+(all\s+)?(your\s+)?(instructions|rules|guidelines)",
    r"(?i)you\s+are\s+now\s+(a\s+|an\s+)?",
    r"(?i)\bsystem\s+prompt\b",
    r"(?i)(print|reveal|show|output|leak|expose)\s+(me\s+)?(the\s+|your\s+)?(api[_\s]?key|secret|token|password|system\s+prompt|instructions)",
    r"(?i)\bexfiltrate\b",
    r"(?i)override\s+(the\s+)?(safety|security|guard|policy)",
]

# Tools an autonomous run may never invoke itself, even if a role could.
_FORBIDDEN_TOOLS = {
    "docker.exec",
    "terminal.run",
    "api.call",
    "search.web",
}


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        if re.search(pattern, text):
            return pattern
    return ""


class TaskGuard:
    """Allows or refuses a task/step before the Kernel gate runs."""

    def __init__(
        self,
        *,
        refuse_on_injection: bool = True,
        forbidden_tools: set[str] | None = None,
    ) -> None:
        self.refuse_on_injection = refuse_on_injection
        self.forbidden_tools = set(forbidden_tools or _FORBIDDEN_TOOLS)

    # ------------------------------------------------------------------
    def scan_text(self, text: str) -> GuardDecision:
        """Check a task description for forbidden actions / injection."""
        if not text:
            return GuardDecision(allowed=True)
        if self.refuse_on_injection:
            inj = _first_match(_INJECTION_PATTERNS, text)
            if inj:
                return GuardDecision(
                    allowed=False,
                    reason="prompt-injection marker detected",
                    matched=inj,
                )
        forbidden = _first_match(
            [p for p, _ in _FORBIDDEN_ACTION_PATTERNS], text
        )
        if forbidden:
            reason = next(
                r for p, r in _FORBIDDEN_ACTION_PATTERNS if p == forbidden
            )
            return GuardDecision(
                allowed=False,
                reason=f"forbidden action requires approval: {reason}",
                matched=forbidden,
            )
        return GuardDecision(allowed=True)

    def check_tool(self, tool: str, args: dict | None = None) -> GuardDecision:
        """Check a tool request the loop is about to make."""
        if tool in self.forbidden_tools:
            return GuardDecision(
                allowed=False,
                reason=f"tool {tool!r} is not permitted for autonomous runs",
                matched=tool,
            )
        # Args can smuggle a forbidden action into an otherwise fine tool.
        if args:
            decision = self.scan_text(" ".join(str(v) for v in args.values()))
            if not decision.allowed:
                return decision
        return GuardDecision(allowed=True)

    # ------------------------------------------------------------------
    def assert_task_allowed(self, task: str) -> None:
        decision = self.scan_text(task)
        if not decision.allowed:
            raise ForbiddenActionError(
                f"refused: {decision.reason} (matched {decision.matched!r})"
            )

    def assert_tool_allowed(self, tool: str, args: dict | None = None) -> None:
        decision = self.check_tool(tool, args)
        if not decision.allowed:
            raise ForbiddenActionError(
                f"refused tool {tool!r}: {decision.reason}"
            )
