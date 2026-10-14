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