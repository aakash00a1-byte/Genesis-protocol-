"""GenesisKernel: the authority that orchestrates the whole pipeline.

The Kernel is the only component allowed to:
  - read/write memory (through the Memory Fabric)
  - route model requests (through the ModelRouter)
  - execute tools (through the ToolGateway)
  - coordinate agents (through the Coordinator, Phase 5)
  - run reflection and QA (Phases 8)

No model, agent, or tool has implicit authority.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from genesis.config.settings import GenesisConfig
from genesis.core import (
    AuditEvent,
    MemoryEntry,
    MemoryScope,
    MemoryWritePolicy,
    RiskLevel,
    ToolResult,
    ToolStatus,
    json_safe,
)
from genesis.exceptions import PermissionDenied
from genesis.memory.provider import MemoryProvider
from genesis.models.registry import ModelRegistry
from genesis.monitoring.health import HealthRegistry, HealthStatus
from genesis.monitoring.metrics import Metrics
from genesis.providers.base import ModelCapability, Provider
from genesis.reflection.reflection import ReflectionEngine
from genesis.resilience.policy import FailureEvent, FailureKind, ResiliencePolicy
from genesis.risk.analyzer import RiskAnalyzer
from genesis.router.router import ModelRouter
from genesis.security.audit import AuditLogger
from genesis.security.permissions import Permission, PolicyEngine
from genesis.tools.gateway import ToolGateway, ToolRequest
from genesis.tools.registry import ToolRegistry
from genesis.transparency.ledger import TransparencyReport

logger = logging.getLogger(__name__)


@dataclass
class KernelRequest:
    task: str
    actor: str = "user"
    role: str = "admin"
    scope: MemoryScope = MemoryScope.TASK
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KernelResponse:
    ok: bool
    result: Any = None
    errors: list[str] = field(default_factory=list)
    memory: list[dict[str, Any]] = field(default_factory=list)
    audit_ids: list[str] = field(default_factory=list)
    qa: dict[str, Any] | None = None
    reflection: dict[str, Any] | None = None
    resilience: dict[str, Any] | None = None
    risk: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return json_safe(self.__dict__)


class GenesisKernel:
    def __init__(
        self,
        *,
        config: GenesisConfig | None = None,
        memory: MemoryProvider | None = None,
        registry: ModelRegistry | None = None,
        router: ModelRouter | None = None,
        tools: ToolRegistry | None = None,
        gateway: ToolGateway | None = None,
        audit: AuditLogger | None = None,
        reflection: ReflectionEngine | None = None,
        policy_engine: PolicyEngine | None = None,
        transparency: TransparencyReport | None = None,
        resilience: ResiliencePolicy | None = None,
        metrics: Metrics | None = None,
        health: HealthRegistry | None = None,
        risk_analyzer: RiskAnalyzer | None = None,
    ) -> None:
        self.config = config or GenesisConfig()
        self.memory = memory or MemoryProvider(self.config.memory)
        self.registry = registry or ModelRegistry()
        self.tools = tools or ToolRegistry()
        self.audit = audit or AuditLogger(enabled=self.config.security.audit_enabled)
        self.reflection = reflection or ReflectionEngine()
        self.policy_engine = policy_engine or PolicyEngine()
        self.transparency = transparency or TransparencyReport()
        self.resilience = resilience or ResiliencePolicy()
        self.metrics = metrics or Metrics()
        self.risk_analyzer = risk_analyzer or RiskAnalyzer()
        self.health_registry = health or HealthRegistry()
        self.gateway = gateway or ToolGateway(
            self.tools,
            policy_engine=self.policy_engine,
            audit=self.audit,
        )
        self.router = router or ModelRouter(
            self.registry,
            factory=self._provider_factory,
            default_provider=self.config.router.default_provider,
            max_fallback_depth=self.config.router.max_fallback_depth,
        )
        # Wired by Phase 5/8/9.
        self.coordinator = None
        self.agent_registry = None
        self.qa = None
        self.security = None
        self.care = None
        self.evolution = None

    # ------------------------------------------------------------------
    # Provider factory (wired to the global factory + adapters)
    # ------------------------------------------------------------------
    def _provider_factory(self, name: str) -> Provider:
        from genesis.providers.factory import get_provider

        return get_provider(name, self.config)

    # ------------------------------------------------------------------
    # Memory access (Kernel is the only memory authority)
    # ------------------------------------------------------------------
    def memory_write(
        self,
        scope: MemoryScope,
        key: str,
        value: Any,
        *,
        policy: MemoryWritePolicy = MemoryWritePolicy.ALWAYS,
        verified: bool = True,
        actor: str = "kernel",
    ) -> MemoryEntry:
        return self.memory.write(
            scope, key, value, policy=policy, verified=verified, actor=actor
        )

    def memory_read(
        self, scope: MemoryScope, key: str, *, actor: str = "kernel"
    ) -> MemoryEntry | None:
        return self.memory.read(scope, key, actor=actor)

    def memory_search(
        self,
        query: str,
        *,
        scopes: list[MemoryScope] | None = None,
        top_k: int | None = None,
        actor: str = "kernel",
    ) -> list[MemoryEntry]:
        return self.memory.search(query, scopes=scopes, top_k=top_k, actor=actor)

    # ------------------------------------------------------------------
    # Tool execution (Kernel is the only tool authority)
    # ------------------------------------------------------------------
    def execute_tool(
        self,
        request: ToolRequest,
        *,
        max_risk: RiskLevel = RiskLevel.LOW,
        timeout_seconds: float | None = None,
    ) -> ToolResult:
        return self.gateway.execute(
            request, max_risk=max_risk, timeout_seconds=timeout_seconds
        )

    def agent_tool_request(
        self,
        tool: str,
        args: dict[str, Any],
        actor: str,
        role: str,
        *,
        cwd: str = "/workspace",
        max_risk: RiskLevel = RiskLevel.MEDIUM,
    ) -> ToolResult:
        """Route an agent's tool request through the normal authority gate.

        This is the *only* way an agent reaches a tool: it builds a ToolRequest
        and hands it to the same gateway as everything else. The risk ceiling is
        bounded (MEDIUM by default) so an agent cannot request a HIGH/CRITICAL
        tool unless the caller raises the ceiling explicitly.
        """
        request = ToolRequest(
            tool=tool, args=dict(args), actor=actor, role=role, cwd=cwd
        )
        result = self.execute_tool(request, max_risk=max_risk)
        self.metrics.incr("kernel.agent_tool_requests")
        if result.status is ToolStatus.SUCCESS:
            self.metrics.incr("kernel.agent_tool_granted")
        else:
            self.metrics.incr("kernel.agent_tool_denied")
        return result

    # ------------------------------------------------------------------
    # Model routing (Kernel is the only model authority)
    # ------------------------------------------------------------------
    def complete(
        self,
        prompt: str,
        capability: ModelCapability,
        *,
        offline: bool | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Any:
        offline = self.config.offline if offline is None else offline
        return self.router.complete(
            prompt,
            capability,
            offline=offline,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # ------------------------------------------------------------------
    # High-level pipeline (used by the API server and E2E scenario)
    # ------------------------------------------------------------------
    def run(self, request: KernelRequest) -> KernelResponse:
        """Run the full pipeline for a user task.

        Pipeline: memory retrieval -> task classification -> planning ->
        model routing -> agent coordination -> tool permission -> sandbox ->
        execution -> reflection -> QA -> memory write -> audit.

        When the Coordinator or QA are not wired (pre-Phase 5/8), the Kernel
        falls back to a direct model completion so the pipeline remains
        functional and testable at every stage.
        """
        errors: list[str] = []
        audit_ids: list[str] = []

        # Transparency: record the routing decision and its expected benefit
        # before doing the work, so it can be checked against the outcome.
        decision = self.transparency.decisions.record(
            actor=request.actor,
            question=f"How should this task be handled? {request.task[:120]}",
            options=["coordinator", "direct_completion"],
            chosen="coordinator" if self.coordinator is not None else "direct_completion",
            rationale=(
                "agent coordinator available for dependency-aware multi-agent work"
                if self.coordinator is not None
                else "no coordinator wired; falling back to direct model completion"
            ),
            expected_benefit="produce a verified result for the task",
        )

        # 1. Memory retrieval
        memory_hits = []
        with self.transparency.failures.capture(
            component="kernel.memory_search",
            what="memory retrieval failed",
            impact="task runs without prior context",
        ):
            memory_hits = self.memory_search(
                request.task, scopes=[request.scope, MemoryScope.PROJECT]
            )

        # 2. Task classification -> capability
        capability = self._classify(request.task)

        # 2b. Risk analysis (offline, advisory). The Kernel stays the authority:
        # the assessment informs the decision, it does not bypass the gate.
        risk_assessment = self.risk_analyzer.analyze_and_alert(
            request.task, source="kernel.task"
        )
        self.metrics.incr("kernel.risk.assessments")
        self.metrics.observe("kernel.risk.score", risk_assessment.score)
        if risk_assessment.escalate:
            self.metrics.incr("kernel.risk.escalations")
        if risk_assessment.delivered is False:
            # Threshold met but no verified alert provider is wired. Recorded,
            # not hidden — the same honesty rule as the failure ledger.
            self.transparency.failures.record(
                component="kernel.risk_alert",
                what="risk alert was not delivered",
                why="no verified alert provider is configured",
                impact=f"level={risk_assessment.level.value} was not broadcast",
            )

        # 3. Planning + agent coordination (Phase 5) or direct completion
        result = None
        if self.coordinator is not None:
            result = self.coordinator.run_task(
                task=request.task,
                capability=capability,
                actor=request.actor,
                role=request.role,
            )
        else:
            try:
                model_result = self.complete(
                    f"Task: {request.task}", capability, offline=self.config.offline
                )
                result = model_result.output
            except Exception as exc:  # noqa: BLE001
                self.transparency.failures.record(
                    component="kernel.model_completion",
                    what="direct model completion failed",
                    why=f"{type(exc).__name__}: {exc}",
                    impact="no result produced for the task",
                )
                errors.append(f"model: {exc}")
                result = None

        # 4. Reflection (bounded)
        reflection_result = None
        if result is not None:
            reflection_result = self.reflection.reflect(
                agent="kernel",
                task_id=request.task[:80],
                result_output=result,
            )

        # 5. Independent QA (Phase 8) — the verifier never trusts the producer.
        qa_result = None
        if self.qa is not None and result is not None:
            qa_result = self.qa.verify(
                task=request.task,
                result=result,
                expected=request.metadata.get("expected"),
                producer_claim=reflection_result.passed if reflection_result else None,
            )
            if not qa_result.passed:
                # Failure escalation: surface the QA verdict rather than
                # presenting an unverified success.
                issues = "; ".join(qa_result.issues or ["verification failed"])
                self.transparency.failures.record(
                    component="kernel.qa",
                    what="independent QA did not pass",
                    why=issues,
                    impact="result is not presented as verified",
                )
                errors.append("qa_failed: " + issues)

        # 6. Memory write (policy-controlled)
        try:
            self.memory_write(
                request.scope,
                f"task:{request.task[:64]}",
                {"task": request.task, "result": result, "ok": not errors},
                policy=MemoryWritePolicy.VERIFIED if errors else MemoryWritePolicy.ALWAYS,
                verified=not errors,
                actor=request.actor,
            )
        except Exception as exc:  # noqa: BLE001
            if not self.config.memory.graceful_failure:
                errors.append(f"memory_write: {exc}")

        # 7. Audit
        event = self.audit.record(
            event_type="kernel.run",
            actor=request.actor,
            action="kernel.run",
            status="success" if not errors else "failure",
            details={
                "task": request.task[:200],
                "capability": capability.value,
                "role": request.role,
                "memory_hits": len(memory_hits),
            },
        )
        audit_ids.append(event.event_id)
        self.metrics.incr("kernel.runs")
        if errors:
            self.metrics.incr("kernel.runs.failed")

        # Close the transparency loop: what did the decision actually deliver?
        self.transparency.decisions.resolve(
            decision.decision_id,
            outcome="success" if not errors else "failure",
            actual_benefit=(
                "task completed and verified" if not errors
                else "task did not complete cleanly: " + "; ".join(errors)
            ),
        )

        # Resilient response: record the failure as an event, take the lesson,
        # and decide whether to carry on — without assigning blame.
        resilience_result = None
        if errors:
            response = self.resilience.respond(
                FailureEvent(
                    component="kernel.run",
                    what="; ".join(errors),
                    kind=FailureKind.UNKNOWN,
                )
            )
            resilience_result = response.to_dict()

        return KernelResponse(
            ok=not errors,
            result=result,
            errors=errors,
            memory=[m.to_dict() for m in memory_hits],
            audit_ids=audit_ids,
            qa=qa_result.to_dict() if qa_result else None,
            reflection=reflection_result.to_dict() if reflection_result else None,
            resilience=resilience_result,
            risk=risk_assessment.to_dict(),
        )

    # ------------------------------------------------------------------
    def _classify(self, task: str) -> ModelCapability:
        lowered = task.lower()
        if any(k in lowered for k in ["code", "implement", "function", "fix bug", "refactor"]):
            return ModelCapability.CODE
        if any(k in lowered for k in ["plan", "design", "architecture", "roadmap"]):
            return ModelCapability.PLANNING
        if any(k in lowered for k in ["research", "search", "investigate", "summarize"]):
            return ModelCapability.RESEARCH
        if any(k in lowered for k in ["test", "verify", "qa", "validate", "check"]):
            return ModelCapability.QA
        return ModelCapability.CHAT

    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        checks = {
            "memory": lambda: (
                HealthStatus.OK,
                f"provider={self.memory.name}",
            ),
            "tools": lambda: (
                HealthStatus.OK if len(self.tools.all()) > 0 else HealthStatus.DEGRADED,
                f"{len(self.tools.all())} tools registered",
            ),
            "audit": lambda: (
                HealthStatus.OK if self.audit.enabled else HealthStatus.DEGRADED,
                f"events={self.audit.count()}",
            ),
            "coordinator": lambda: (
                HealthStatus.OK if self.coordinator is not None else HealthStatus.DEGRADED,
                "wired" if self.coordinator is not None else "not wired",
            ),
            "qa": lambda: (
                HealthStatus.OK if self.qa is not None else HealthStatus.DEGRADED,
                "wired" if self.qa is not None else "not wired",
            ),
        }
        for name, checker in checks.items():
            self.health_registry.register(name, checker)
        report = self.health_registry.to_dict()
        return {
            "app": self.config.app_name,
            "version": self.config.version,
            "env": self.config.env.value,
            "offline": self.config.offline,
            "memory_provider": self.memory.name,
            "tools": len(self.tools.all()),
            "audit_events": self.audit.count(),
            "health": report,
            "metrics": self.metrics.snapshot(),
        }