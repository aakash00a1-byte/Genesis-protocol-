"""Genesis V5 configuration management.

Supports Development, Testing, and Production environments through
configuration rather than hard-coded values. Secrets are never embedded in
this file; they resolve through a `resolve_secret` indirection so the system
can stay fully offline and secret-free in test environments.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from genesis.evolution.evolution import EvolutionConfig


class Env(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class MemoryConfig:
    provider: str = "local"  # local | mempalace (adapter boundary)
    max_entries_per_scope: int = 1000
    relevance_top_k: int = 5
    graceful_failure: bool = True
    redact_secrets: bool = True
    mempalace_endpoint: str = ""  # not set by default; adapter stays disabled
    mempalace_api_key_env: str = "GENESIS_MEMPALACE_API_KEY"


@dataclass
class RouterConfig:
    default_provider: str = "mock"
    fallback_providers: list[str] = field(
        default_factory=lambda: ["mock", "openhandssdk"]
    )
    max_fallback_depth: int = 3
    prefer_capability: bool = True


@dataclass
class ToolConfig:
    enabled: bool = True
    default_timeout_seconds: float = 30.0
    sandbox_root_allow: list[str] = field(default_factory=lambda: ["/workspace"])
    deny_destructive_without_permission: bool = True


@dataclass
class AgentConfig:
    max_retries: int = 3
    retry_backoff_base: float = 0.5
    coordinated: bool = True


@dataclass
class SecurityConfig:
    rate_limit_per_minute: int = 120
    max_request_bytes: int = 1_000_000
    audit_enabled: bool = True
    zero_trust: bool = True
    # Standing, bounded auto-grants. Empty by default: the gate is fully
    # enforced. When set, only these permissions are auto-granted to the named
    # actor, and only at LOW risk. This never disables the gate; it removes a
    # per-call approval for a pre-authorised, low-risk, read-only capability.
    auto_grant_actor: str = "autonomy"
    auto_grant_permissions: list[str] = field(default_factory=list)
    # Ceiling for auto-granted calls. Kept at LOW deliberately; a standing
    # grant must not become a path to a HIGH/CRITICAL action.
    auto_grant_max_risk: str = "low"


@dataclass
class StorageConfig:
    """Persistent storage + backup strategy."""

    data_dir: str = "./data"
    memory_file: str = "memory.json"
    backup_enabled: bool = True
    backup_dir: str = "./data/backups"
    backup_interval_seconds: int = 3600
    max_backups: int = 10


@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = "%(asctime)s %(levelname)s %(name)s %(message)s"
    json: bool = False
    file: str = ""  # empty => stderr only


@dataclass
class RuntimeConfig:
    """Worker lifecycle and resource limits."""

    max_workers: int = 4
    shutdown_timeout_seconds: float = 10.0
    max_memory_entries: int = 1000
    request_timeout_seconds: float = 60.0


@dataclass
class AutonomyConfig:
    """Bounded autonomous task-execution loop.

    Off by default: the loop only runs when explicitly enabled, and even then
    it drives the existing Kernel (no new execution path). Every bound has a
    finite default so a run always terminates.
    """

    enabled: bool = False
    max_iterations: int = 5
    max_retries_per_step: int = 2
    max_wall_clock_seconds: float = 120.0
    # Upper bound on a single iteration; a hung step is cut off, not waited on.
    step_timeout_seconds: float = 30.0
    checkpoint_dir: str = "./data/autonomy"
    # An autonomous run never escalates risk above this, regardless of role.
    max_risk: str = "medium"
    # Refuse to run a task whose text looks like a prompt-injection attempt.
    refuse_on_injection: bool = True
    # Read-only reconnaissance tools the loop may run without a human in the
    # loop. Each call still travels the full gate; the standing grant only
    # removes a per-call approval. Writes and exec tools are never listed here.
    read_only_permissions: list[str] = field(
        default_factory=lambda: [
            "file.read",
            "file.list",
            "git.read",
        ]
    )


@dataclass
class IntegrationConfig:
    """Chat-platform integration (Discord/Telegram) into the Kernel.

    Off by default. No transport is constructed unless its token is present,
    and an inbound message is only accepted from an allow-listed channel. The
    message is never executed directly: it is parsed into a command and routed
    through the same governed paths as any other request (the authority
    pipeline for tool requests, the bounded autonomy loop for tasks).
    """

    enabled: bool = False
    # Proposals generated per /generate; small by default so a chat reply is
    # fast. The generation path has no side effects regardless.
    shots: int = 8
    poll_interval_seconds: float = 2.0
    rate_limit_per_minute: int = 30
    # Reject an inbound message longer than this before it reaches the guard or
    # a command parser, so an oversized payload cannot exhaust parsing.
    max_message_chars: int = 4000
    # Allow-listed channels/chats. Empty means "refuse everything" — a chat
    # integration must be told explicitly which rooms it may answer.
    allowed_channels: list[str] = field(default_factory=list)
    # The role a chat request runs as. Defaults to the zero-trust role, so a
    # chat message cannot reach a tool unless a standing grant or the role
    # explicitly allows it.
    default_role: str = "none"

    discord_enabled: bool = False
    discord_bot_token: str = ""
    discord_api_base: str = "https://discord.com/api/v10"

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"


@dataclass
class GenesisConfig:
    env: Env = Env.DEVELOPMENT
    app_name: str = "genesis-v5"
    version: str = "5.0.0"
    offline: bool = True
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    router: RouterConfig = field(default_factory=RouterConfig)
    tools: ToolConfig = field(default_factory=ToolConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    autonomy: AutonomyConfig = field(default_factory=AutonomyConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)

    @property
    def is_production(self) -> bool:
        return self.env == Env.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.env == Env.TESTING

    @classmethod
    def from_env(cls) -> "GenesisConfig":
        env_name = os.getenv("GENESIS_ENV", "development").lower()
        try:
            env = Env(env_name)
        except ValueError:
            env = Env.DEVELOPMENT

        cfg = cls(env=env)
        cfg.offline = _env_bool("GENESIS_OFFLINE", True)
        cfg.memory = MemoryConfig(
            provider=os.getenv("GENESIS_MEMORY_PROVIDER", "local"),
            max_entries_per_scope=_env_int(
                "GENESIS_MEMORY_MAX_ENTRIES", 1000
            ),
            relevance_top_k=_env_int("GENESIS_MEMORY_TOP_K", 5),
            graceful_failure=_env_bool("GENESIS_MEMORY_GRACE", True),
            redact_secrets=_env_bool("GENESIS_MEMORY_REDACT", True),
            mempalace_endpoint=os.getenv("GENESIS_MEMPALACE_ENDPOINT", ""),
            mempalace_api_key_env=os.getenv(
                "GENESIS_MEMPALACE_KEY_ENV", "GENESIS_MEMPALACE_API_KEY"
            ),
        )
        cfg.router = RouterConfig(
            default_provider=os.getenv("GENESIS_ROUTER_DEFAULT", "mock"),
            fallback_providers=[
                p.strip()
                for p in os.getenv(
                    "GENESIS_ROUTER_FALLBACK",
                    "mock,openhandssdk",
                ).split(",")
            ],
            max_fallback_depth=_env_int("GENESIS_ROUTER_MAX_FALLBACK", 3),
        )
        cfg.security = SecurityConfig(
            rate_limit_per_minute=_env_int("GENESIS_RATE_LIMIT", 120),
            max_request_bytes=_env_int("GENESIS_MAX_REQUEST_BYTES", 1_000_000),
            audit_enabled=_env_bool("GENESIS_AUDIT_ENABLED", True),
            zero_trust=_env_bool("GENESIS_ZERO_TRUST", True),
            auto_grant_actor=os.getenv("GENESIS_AUTO_GRANT_ACTOR", "autonomy"),
            auto_grant_permissions=[
                p.strip()
                for p in os.getenv("GENESIS_AUTO_GRANT_PERMISSIONS", "").split(",")
                if p.strip()
            ],
            auto_grant_max_risk=os.getenv("GENESIS_AUTO_GRANT_MAX_RISK", "low"),
        )
        cfg.autonomy = AutonomyConfig(
            enabled=_env_bool("GENESIS_AUTONOMY_ENABLED", False),
            max_iterations=_env_int("GENESIS_AUTONOMY_MAX_ITERATIONS", 5),
            max_retries_per_step=_env_int("GENESIS_AUTONOMY_MAX_RETRIES", 2),
            max_wall_clock_seconds=float(
                _env_int("GENESIS_AUTONOMY_MAX_SECONDS", 120)
            ),
            step_timeout_seconds=float(
                _env_int("GENESIS_AUTONOMY_STEP_SECONDS", 30)
            ),
            checkpoint_dir=os.getenv(
                "GENESIS_AUTONOMY_CHECKPOINT_DIR", "./data/autonomy"
            ),
            max_risk=os.getenv("GENESIS_AUTONOMY_MAX_RISK", "medium"),
            refuse_on_injection=_env_bool(
                "GENESIS_AUTONOMY_REFUSE_INJECTION", True
            ),
            read_only_permissions=[
                p.strip()
                for p in os.getenv(
                    "GENESIS_AUTONOMY_READ_ONLY_PERMISSIONS",
                    "file.read,file.list,git.read",
                ).split(",")
                if p.strip()
            ],
        )
        cfg.integration = IntegrationConfig(
            enabled=_env_bool("GENESIS_INTEGRATION_ENABLED", False),
            shots=_env_int("GENESIS_INTEGRATION_SHOTS", 8),
            poll_interval_seconds=float(
                _env_int("GENESIS_INTEGRATION_POLL_SECONDS", 2)
            ),
            rate_limit_per_minute=_env_int(
                "GENESIS_INTEGRATION_RATE_LIMIT", 30
            ),
            allowed_channels=[
                c.strip()
                for c in os.getenv(
                    "GENESIS_INTEGRATION_ALLOWED_CHANNELS", ""
                ).split(",")
                if c.strip()
            ],
            default_role=os.getenv("GENESIS_INTEGRATION_DEFAULT_ROLE", "none"),
            discord_enabled=_env_bool("GENESIS_DISCORD_ENABLED", False),
            discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", ""),
            discord_api_base=os.getenv(
                "GENESIS_DISCORD_API_BASE", "https://discord.com/api/v10"
            ),
            telegram_enabled=_env_bool("GENESIS_TELEGRAM_ENABLED", False),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_api_base=os.getenv(
                "GENESIS_TELEGRAM_API_BASE", "https://api.telegram.org"
            ),
        )
        return cfg


def resolve_secret(name: str, cfg: GenesisConfig | None = None) -> str | None:
    """Resolve a secret name to a value without printing it.

    In Production the value must come from the environment; in Development/
    Testing it may also come from an in-memory store injected by the caller.
    Returns None when unavailable — callers must treat None as 'not
    configured' and keep the integration disabled.
    """
    raw = os.getenv(name)
    if raw:
        return raw
    return None


def load_config() -> GenesisConfig:
    """Load config from environment; caches on first call."""
    return GenesisConfig.from_env()


_CONFIG_CACHE: GenesisConfig | None = None


def get_config() -> GenesisConfig:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_config()
    return _CONFIG_CACHE


def _reset_config_cache() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
