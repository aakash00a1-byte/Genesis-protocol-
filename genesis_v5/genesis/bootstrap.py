"""Genesis V5 application wiring.

Builds a fully-wired system from configuration:
  config -> memory -> models -> tools -> gateway -> router -> kernel.

Offline by default. No network access, no credentials required.
"""
from __future__ import annotations

from genesis.adapters.registration import register_default_adapters
from genesis.agents.builtin import register_builtin_agents
from genesis.agents.registry import AgentRegistry
from genesis.care.companion import CareCompanion
from genesis.config.settings import GenesisConfig
from genesis.core import RiskLevel
from genesis.coordinator.coordinator import AgentCoordinator, CoordinatorConfig
from genesis.kernel.kernel import GenesisKernel
from genesis.memory.provider import MemoryProvider
from genesis.models.registry import default_registry
from genesis.planning.planner import Planner
from genesis.providers.factory import get_factory
from genesis.qa.verifier import IndependentVerifier, VerifierConfig
from genesis.resilience.policy import ResiliencePolicy
from genesis.router.router import ModelRouter
from genesis.security.audit import AuditLogger
from genesis.security.core import SecurityCore
from genesis.security.permissions import PolicyEngine
from genesis.security.ratelimit import RateLimiter
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
    gateway = ToolGateway(
        tools,
        policy_engine=policy_engine,
        audit=audit,
        auto_grant_actor=cfg.security.auto_grant_actor,
        auto_grant_permissions=cfg.security.auto_grant_permissions,
        auto_grant_max_risk=_risk_level(cfg.security.auto_grant_max_risk),
    )
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
