"""ToolGateway: the single execution chokepoint.

Flow enforced here:
  ToolRequest -> Policy Check -> Permission Gate -> Sandbox -> Execute ->
  Result -> Audit.

No model or agent bypasses this gateway.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from genesis.core import AuditEvent, RiskLevel, ToolResult, ToolStatus
from genesis.exceptions import PermissionDenied, SandboxViolation, ToolTimeout
from genesis.security.audit import AuditLogger
from genesis.security.permissions import PolicyEngine
from genesis.security.validation import InputValidator

from .registry import ToolContext, ToolRegistry, ToolSpec
from .sandbox import Sandbox

logger = logging.getLogger(__name__)


@dataclass
class ToolRequest:
    tool: str
    args: dict[str, Any]
    actor: str = "unknown"
    role: str = "none"
    cwd: str = "/workspace"
    allow_list_overrides: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": dict(self.args),
            "actor": self.actor,
            "role": self.role,
            "cwd": self.cwd,
        }


class ToolGateway:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        policy_engine: PolicyEngine | None = None,
        audit: AuditLogger | None = None,
        sandbox: Sandbox | None = None,
        validator: InputValidator | None = None,
        auto_grant_actor: str | None = None,
        auto_grant_permissions: list[str] | None = None,
        auto_grant_max_risk: RiskLevel = RiskLevel.LOW,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit = audit or AuditLogger()
        self.sandbox = sandbox or Sandbox()
        self.validator = validator or InputValidator()
        self._auto_grant_actor = (auto_grant_actor or "").strip()
        self._auto_grant = frozenset(
            p.strip() for p in (auto_grant_permissions or []) if p.strip()
        )
        self._auto_grant_max_risk = auto_grant_max_risk
        # Tools the kernel-side authority refuses outright, regardless of role or
        # risk ceiling. This is the gate's enforcement of the autonomy guard's
        # forbidden-tool list, so it cannot be bypassed by a role (e.g. an admin
        # agent asking for docker.exec) on the agent path.
        self._forbidden_tools: frozenset[str] = frozenset()

    def forbid_tools(self, names: list[str] | set[str] | frozenset[str]) -> None:
        """Refuse these tools at the gate, for every actor and role."""
        self._forbidden_tools = frozenset(str(n) for n in names if str(n).strip())

    # ------------------------------------------------------------------
    def execute(
        self,
        request: ToolRequest,
        *,
        max_risk: RiskLevel = RiskLevel.LOW,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        """Execute a tool request through the full gate pipeline."""
        start = time.time()
        spec = self.registry.get(request.tool)

        # 1. Identity check
        if spec is None:
            return self._finish(
                ToolResult(
                    tool=request.tool,
                    status=ToolStatus.MALFORMED,
                    error="unknown tool",
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_denied",
                    actor=request.actor,
                    action=f"tool.{request.tool}",
                    status="denied",
                    details={"reason": "unknown_tool", "role": request.role},
                ),
            )
        if not spec.enabled:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.DENIED,
                    error="tool disabled",
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_denied",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="denied",
                    details={"reason": "tool_disabled", "role": request.role},
                ),
            )

        # 2. Input validation (malformed request)
        validation = self.validator.validate_tool_request(spec.name, request.args)
        if not validation.ok:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.MALFORMED,
                    error="; ".join(validation.errors),
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_malformed",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="malformed",
                    details={"errors": validation.errors, "role": request.role},
                ),
            )

        # 2b. Forbidden tools are refused for every actor and role, before any
        # permission or risk consideration. This is not a bypassable policy.
        if spec.name in self._forbidden_tools:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.DENIED,
                    error="tool is forbidden by the authority gate",
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_denied",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="denied",
                    risk_level=spec.risk_level.value,
                    details={"reason": "forbidden_tool", "role": request.role},
                ),
            )

        # 3. Policy check + permission gate
        allowed = self._granted(request, spec, max_risk)
        if not allowed:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.DENIED,
                    error="permission denied",
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_denied",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="denied",
                    risk_level=spec.risk_level.value,
                    details={"reason": "permission", "role": request.role},
                ),
            )

        # 4. Sandbox boundary
        try:
            self.sandbox.check(
                spec.name, request.args, category=spec.category.value
            )
        except SandboxViolation as exc:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.SANDBOX_VIOLATION,
                    error=str(exc),
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="sandbox_violation",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="sandbox_violation",
                    risk_level="critical",
                    details={"reason": str(exc), "role": request.role},
                ),
            )

        # 5. Execute (with timeout)
        handler = self.registry.handler(spec.name)
        if handler is None:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.FAILURE,
                    error="no handler registered",
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_failure",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="failure",
                    risk_level=spec.risk_level.value,
                    details={"reason": "no_handler"},
                ),
            )

        timeout = timeout_seconds or spec.timeout_seconds
        try:
            result = self._run_with_timeout(handler, request, spec, timeout)
        except ToolTimeout as exc:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.TIMEOUT,
                    error=str(exc),
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_timeout",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="timeout",
                    risk_level=spec.risk_level.value,
                    details={"timeout_seconds": timeout},
                ),
            )
        except PermissionDenied as exc:
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.DENIED,
                    error=str(exc),
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_denied",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="denied",
                    risk_level=spec.risk_level.value,
                    details={"reason": str(exc)},
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("tool %s failed for actor %s", spec.name, request.actor)
            return self._finish(
                ToolResult(
                    tool=spec.name,
                    status=ToolStatus.FAILURE,
                    error=str(exc),
                    risk_level=spec.risk_level,
                    duration_ms=self._elapsed(start),
                ),
                AuditEvent(
                    event_type="tool_failure",
                    actor=request.actor,
                    action=f"tool.{spec.name}",
                    status="failure",
                    risk_level=spec.risk_level.value,
                    details={"reason": "handler_exception", "error": str(exc)[:500]},
                ),
            )

        # 6. Success
        return self._finish(
            ToolResult(
                tool=spec.name,
                status=ToolStatus.SUCCESS,
                result=result,
                risk_level=spec.risk_level,
                duration_ms=self._elapsed(start),
                sandboxed=True,
            ),
            AuditEvent(
                event_type="tool_exec",
                actor=request.actor,
                action=f"tool.{spec.name}",
                status="success",
                risk_level=spec.risk_level.value,
                details={"role": request.role, "duration_ms": self._elapsed(start)},
            ),
        )

    # ------------------------------------------------------------------
    def _granted(self, request: ToolRequest, spec: ToolSpec, max_risk: RiskLevel) -> bool:
        if request.role.lower() == "kernel":
            # The Kernel is the orchestrator, not a free-air grant: it still
            # goes through the risk ceiling.
            return spec.risk_level.rank() <= max_risk.rank()
        if self._is_auto_granted(request, spec):
            return True
        return self.policy_engine.check(
            permission=spec.permission,
            role_name=request.role,
            max_risk=max_risk,
            risk=spec.risk_level,
        )

    def _is_auto_granted(self, request: ToolRequest, spec: ToolSpec) -> bool:
        """A narrow standing grant: same actor AND a pre-listed permission AND
        the tool is at or below the LOW risk ceiling. All three must hold, so a
        standing grant can never reach a write or a HIGH/CRITICAL tool."""
        if not self._auto_grant or request.actor != self._auto_grant_actor:
            return False
        if spec.permission.value not in self._auto_grant:
            return False
        return spec.risk_level.rank() <= self._auto_grant_max_risk.rank()

    def _run_with_timeout(
        self,
        handler: Any,
        request: ToolRequest,
        spec: ToolSpec,
        timeout: float,
    ) -> Any:
        context = ToolContext(
            actor=request.actor,
            role=request.role,
            sandbox=self.sandbox,
            cwd=request.cwd,
            audit=self.audit,
        )
        result_holder: dict[str, Any] = {}
        error_holder: dict[str, Any] = {}

        def _target() -> None:
            try:
                result_holder["value"] = handler(context, dict(request.args))
            except Exception as exc:  # noqa: BLE001
                error_holder["error"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout=max(0.001, timeout))
        if thread.is_alive():
            raise ToolTimeout(
                f"tool {spec.name} exceeded timeout {timeout}s"
            )
        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("value")

    def _finish(self, result: ToolResult, event: AuditEvent) -> ToolResult:
        result.audit_event = event
        self.audit.record_event(event)
        return result

    @staticmethod
    def _elapsed(start: float) -> int:
        return int((time.time() - start) * 1000)
