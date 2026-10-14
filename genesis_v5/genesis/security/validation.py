"""Input and output validation."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

_MAX_DEFAULT = 1_000_000


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


class InputValidator:
    """Validates tool/memory/agent inputs.

    Rejects oversized payloads and embedded control characters that indicate
    malformed or prompt-injection-style requests.
    """

    def __init__(self, max_bytes: int = _MAX_DEFAULT) -> None:
        self.max_bytes = max_bytes

    def validate_tool_request(self, tool_name: str, args: dict[str, Any]) -> ValidationResult:
        errors: list[str] = []
        if not isinstance(tool_name, str) or not tool_name.strip():
            errors.append("tool name must be a non-empty string")
        if not isinstance(args, dict):
            errors.append("tool arguments must be an object")
        else:
            try:
                size = len(str(args).encode("utf-8"))
            except Exception:  # noqa: BLE001
                size = len(str(args))
            if size > self.max_bytes:
                errors.append(f"request exceeds max bytes {self.max_bytes}")
        return ValidationResult(ok=not errors, errors=errors)

    def contains_injection_markers(self, text: str) -> bool:
        """Heuristic detection of prompt-injection-like requests.

        Detects attempts to override system instructions or exfiltrate
        credentials inside tool arguments.
        """
        lowered = (text or "").lower()
        patterns = [
            r"ignore (all )?(previous|prior) instructions",
            r"you are now (a|an|the) (free |unfettered )?",
            r"disregard (your|the) (system|guidelines|instructions)",
            r"(reveal|print|show|leak|expose) (the |your )?(api[_-]?key|token|secret|password)",
        ]
        return any(re.search(p, lowered) for p in patterns)


class OutputValidator:
    """Validates model/tool outputs.

    Ensures outputs do not leak secrets and do not exceed size limits.
    """

    def __init__(self, max_bytes: int = _MAX_DEFAULT) -> None:
        self.max_bytes = max_bytes

    def validate_output(self, output: Any) -> ValidationResult:
        errors: list[str] = []
        text = str(output)
        if len(text.encode("utf-8", errors="ignore")) > self.max_bytes:
            errors.append("output exceeds max bytes")
        return ValidationResult(ok=not errors, errors=errors)

    def contains_secret(self, output: Any) -> bool:
        from genesis.core import SECRET_PATTERNS

        text = str(output)
        return any(re.search(p, text) for p in SECRET_PATTERNS)


_default_input = InputValidator()
_default_output = OutputValidator()


def validate_input(*args: Any, **kwargs: Any) -> ValidationResult:
    return _default_input.validate_tool_request(*args, **kwargs)


def validate_output(output: Any) -> ValidationResult:
    return _default_output.validate_output(output)