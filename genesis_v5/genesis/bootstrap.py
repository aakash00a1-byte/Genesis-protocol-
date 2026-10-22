"""Genesis V5 application wiring.

Builds a fully-wired system from configuration:
  config -> memory -> models -> tools -> gateway -> router -> kernel.

Offline by default. No network access, no credentials required.
"""
from __future__ import annotations

from genesis.adapters.registration import register_default_adapters
from genesis.agents.builtin import register_builtin_agents
from genesis.agents.registry import AgentRegistry
from genesis.autonomy.guard import TaskGuard
from genesis.autonomy.loop import AutonomousLoop
from genesis.care.companion import CareCompanion
from genesis.config.settings import GenesisConfig
from genesis.coordinator.coordinator import AgentCoordinator, CoordinatorConfig
from genesis.core import RiskLevel
from genesis.evolution.evolution import EvolutionAgent, ProposalStore
from genesis.evolution.signals import SignalCollector
from genesis.generation.generator import ParallelGenerator
from genesis.integration.gateway import ChatGateway
from genesis.kernel.kernel import GenesisKernel
from genesis.memory.provider import MemoryProvider
from genesis.models.registry import default_registry
from genesis.pipeline.authority import AuthorityPipeline
from genesis.planning.planner import Planner
from genesis.providers.factory import get_factory
from genesis.qa.verifier import IndependentVerifier, VerifierConfig
from genesis.resilience.policy import ResiliencePolicy
from genesis.router.router import ModelRouter
from genesis.security.audit import AuditLogger
from genesis.security.core import SecurityCore
from genesis.security.permissions import PolicyEngine
from genesis.security.ratelimit import RateLimiter
from genesis.service.http import GenesisService
from genesis.tools.builtin import build_default_registry
from genesis.tools.gateway import ToolGateway
from genesis.transparency.ledger import TransparencyReport


def _risk_level(name: str) -> RiskLevel:
    try:
        return RiskLevel(name.strip().lower())
    except ValueError:
        return RiskLevel.LOW


def build(
    config: GenesisConfig | None = None,
    *,
    register_adapters: bool = True,
    with_coordinator: bool = True,
    with_qa: bool = True,
) -> GenesisKernel:
    cfg = config or GenesisConfig()
    if register_adapters:
        register_default_adapters()

    memory = MemoryProvider(cfg.memory)
    registry = default_registry(cfg)
    tools = build_default_registry()
    audit = AuditLogger(enabled=cfg.security.audit_enabled)
    policy_engine = PolicyEngine()
    transparency = TransparencyReport()
    resilience = ResiliencePolicy(max_continuations=cfg.agents.max_retries)
    care = CareCompanion()
    # Standing, bounded auto-grants. Off unless explicitly configured. When the
    # autonomy loop is enabled, its read-only recon permissions are granted to
    # the autonomy actor so recon needs no per-call approval — but the gateway
    # still enforces the LOW risk ceiling, so writes/exec are never covered.
    auto_grant_permissions = list(cfg.security.auto_grant_permissions)
    if cfg.autonomy.enabled:
        auto_grant_permissions = sorted(
            set(auto_grant_permissions) | set(cfg.autonomy.read_only_permissions)
        )
    gateway = ToolGateway(
        tools,
        policy_engine=policy_engine,
        audit=audit,
        auto_grant_actor=cfg.security.auto_grant_actor,
        auto_grant_permissions=auto_grant_permissions,
        auto_grant_max_risk=_risk_level(cfg.security.auto_grant_max_risk),
    )
    if cfg.autonomy.enabled:
        # Make the autonomy guard's forbidden-tool list a hard gate rule, not
        # just a pre-check the loop performs. Then no actor/role (including an
        # admin agent) can reach docker.exec / terminal.run / api.call /
        # search.web on the agent path while autonomy is enabled.
        gateway.forbid_tools(TaskGuard().forbidden_tools)
    factory = get_factory()
    router = ModelRouter(
        registry,
        factory=lambda name: factory.create(name, cfg),
        default_provider=cfg.router.default_provider,
        max_fallback_depth=cfg.router.max_fallback_depth,
    )

    kernel = GenesisKernel(
        config=cfg,
        memory=memory,
        registry=registry,
        router=router,
        tools=tools,
        gateway=gateway,
        audit=audit,
        policy_engine=policy_engine,
        transparency=transparency,
        resilience=resilience,
    )
    kernel.care = care

    if with_coordinator:
        agent_registry = AgentRegistry()
        register_builtin_agents(agent_registry)
        planner = Planner()
        coordinator = AgentCoordinator(
            agent_registry,
            planner,
            CoordinatorConfig(
                max_retries=cfg.agents.max_retries,
                retry_backoff_base=cfg.agents.retry_backoff_base,
            ),
            # Agents can now *ask* for a tool; the request travels the Kernel's
            # authority gate (policy, permission, sandbox, audit) like any other.
            tool_request=kernel.agent_tool_request,
        )
        kernel.coordinator = coordinator
        kernel.agent_registry = agent_registry

    if cfg.evolution.enabled:
        # Self-improvement is wired only when explicitly enabled. It observes
        # the transparency ledgers and metrics and proposes bounded changes; it
        # is given no tool gateway, so it cannot act on anything even in
        # principle. A human reviews the proposals.
        collector = SignalCollector(
            failure_ledger=transparency.failures,
            decision_ledger=transparency.decisions,
            metrics=kernel.metrics,
        )
        store = ProposalStore(cfg.evolution.store_dir) if cfg.evolution.persist else None
        kernel.evolution = EvolutionAgent(
            config=cfg.evolution,
            collector=collector,
            store=store,
            memory=kernel.memory,
        )

    if with_qa:
        kernel.qa = IndependentVerifier(
            VerifierConfig(
                max_correction_iterations=cfg.agents.max_retries,
                pass_threshold=0.6,
            )
        )

    if cfg.security.zero_trust:
        kernel.security = SecurityCore(
            audit=AuditLogger(enabled=cfg.security.audit_enabled),
            limiter=RateLimiter(limit_per_minute=cfg.security.rate_limit_per_minute),
        )

    return kernel


def build_chat_gateway(
    kernel: GenesisKernel,
    *,
    config: GenesisConfig | None = None,
    generator: ParallelGenerator | None = None,
    loop: AutonomousLoop | None = None,
) -> ChatGateway:
    """Wire the chat gateway onto an already-built kernel.

    The gateway reuses the kernel's gateway/pipeline and the bounded autonomy
    loop; it never bypasses either. When the autonomy loop is not supplied it
    is built only if ``config.autonomy.enabled`` is set.
    """
    cfg = config or GenesisConfig()
    gen = generator or ParallelGenerator(num_qubits=3)
    pipeline = AuthorityPipeline(gen, kernel.gateway)
    service = GenesisService(gen, pipeline)
    active_loop = loop
    if active_loop is None and cfg.autonomy.enabled:
        active_loop = AutonomousLoop(kernel, cfg.autonomy)
    return ChatGateway(config=cfg.integration, service=service, loop=active_loop)


__all__ = ["build", "build_chat_gateway"]
