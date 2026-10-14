"""Genesis V5 shared primitives."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

SECRET_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password|passwd|credential)\s*[=:]\s*['\"]?[A-Za-z0-9_\-\.]{6,}['\"]?",
    r"(?i)bearer\s+[A-Za-z0-9_\-\.]{8,}",
    r"gAAAA[A-Za-z0-9_\-\.]{20,}",
]


_RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    def rank(self) -> int:
        return _RISK_RANK.get(self.value, 0)


class ToolStatus(str, Enum):
    SUCCESS = "success"
    DENIED = "denied"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    MALFORMED = "malformed"
    SANDBOX_VIOLATION = "sandbox_violation"


class MemoryScope(str, Enum):
    SESSION = "session"
    TASK = "task"
    PROJECT = "project"
    LONG_TERM = "long_term"


class MemoryWritePolicy(str, Enum):
    ALWAYS = "always"
    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    NEVER = "never"
    VERIFIED = "verified"


def now_ms() -> int:
    return int(time.time() * 1000)


def new_id(prefix: str = "evt") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def sanitize_text(text: str, redact_secrets: bool = True) -> str:
    """Redact common secret patterns from a string."""
    if not redact_secrets:
        return text
    import re

    result = text
    for pattern in SECRET_PATTERNS:
        result = re.sub(pattern, "[REDACTED]", result)
    return result


def json_safe(value: Any) -> Any:
    """Best-effort conversion to JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    return str(value)


@dataclass
class AuditEvent:
    """A structured, immutable audit record.

    Rich constructor for flagged policy/security events.
    """

    event_type: str
    actor: str
    action: str
    resource: str = ""
    status: str = "success"
    risk_level: str = "low"
    details: dict[str, Any] = field(default_factory=dict)
    actor_role: str = "agent"
    actor_is_model: bool = False
    timestamp_ms: int = field(default_factory=now_ms)
    event_id: str = field(default_factory=lambda: new_id("aud"))
    allow_list_override: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass
class MemoryEntry:
    scope: MemoryScope
    key: str
    value: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    created_ms: int = field(default_factory=now_ms)
    updated_ms: int = field(default_factory=now_ms)
    version: int = 1
    entry_id: str = field(default_factory=lambda: new_id("mem"))
    secret_redacted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass
class ModelResult:
    provider: str
    model: str
    output: str
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    raw: Any = None
    status: str = "success"  # success | error | fallback | refused

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


@dataclass
class ToolResult:
    tool: str
    status: ToolStatus
    result: Any = None
    error: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    duration_ms: int = 0
    audit_event: Optional[AuditEvent] = None
    sandboxed: bool = True

    @property
    def ok(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)