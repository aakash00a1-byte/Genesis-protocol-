"""Secret redaction."""
from __future__ import annotations

import re

from genesis.core import SECRET_PATTERNS

# Ordered: specific patterns first so the generic key-value pattern cannot
# consume a prefix like "Bearer" and leave the actual token exposed.
_AUTHORIZATION_BEARER_PATTERN = re.compile(
    r"(?i)authorization[\"']?\s*[:=]\s*[\"']?bearer\s+[A-Za-z0-9_\-\.+/]{8,}[\"']?"
)
_BEARER_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.+/]{8,}")
_SK_PREFIX_PATTERN = re.compile(r"(?i)\bsk-[A-Za-z0-9_\-\.+/]{8,}")
_TOKEN_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|credential|authorization)"
    r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.+/]{6,}[\"']?"
)
_FERNET_PATTERN = re.compile(r"gAAAA[A-Za-z0-9_\-\.]{20,}")


class Redactor:
    def __init__(self, patterns: list[re.Pattern] | None = None) -> None:
        self._patterns = patterns or [
            _AUTHORIZATION_BEARER_PATTERN,
            _BEARER_PATTERN,
            _SK_PREFIX_PATTERN,
            _TOKEN_PATTERN,
            _FERNET_PATTERN,
        ]

    def redact(self, text: str) -> str:
        if not text:
            return text
        result = text
        for pattern in self._patterns:
            result = pattern.sub("[REDACTED]", result)
        return result

    def redact_object(self, obj: object) -> object:
        if isinstance(obj, str):
            return self.redact(obj)
        if isinstance(obj, dict):
            return {self.redact(k): self.redact_object(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.redact_object(v) for v in obj]
        return obj


_default = Redactor()


def redact(text: str) -> str:
    return _default.redact(text)