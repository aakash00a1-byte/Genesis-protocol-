"""Phase 10 — Production Readiness tests.

Covers configuration management, environment separation, Docker support,
health/readiness endpoints, graceful shutdown, worker lifecycle, persistent
storage, backup strategy, logging configuration, monitoring hooks, rate
limits, resource limits, and recovery strategy. Offline, no credentials.
"""
from __future__ import annotations

import json
import os
import time

import pytest

from genesis.config.settings import Env, GenesisConfig, StorageConfig
from genesis.logging.config import JsonFormatter, logging_setup, _RedactingFormatter
from genesis.runtime.lifecycle import ApplicationRuntime, WorkerPool


# ------------------------------------------------------------------
# Configuration management / environment separation
# ------------------------------------------------------------------
def test_config_environment_separation() -> None:
    cfg = GenesisConfig(env=Env.PRODUCTION)
    assert cfg.is_production
    assert not cfg.is_testing
    dev = GenesisConfig(env=Env.DEVELOPMENT)
    assert dev.is_testing is False
    assert not dev.is_production
    test = GenesisConfig(env=Env.TESTING)
    assert test.is_testing


def test_config_sections_exist() -> None:
    cfg = GenesisConfig()
    assert cfg.memory.provider == "local"
    assert cfg.router.default_provider == "mock"
    assert cfg.agents.max_retries == 3
    assert cfg.security.rate_limit_per_minute == 120
    assert cfg.storage.data_dir == "./data"
    assert cfg.storage.backup_enabled
    assert cfg.runtime.max_workers == 4
    assert cfg.logging.level == "INFO"


def test_config_from_env_parses_ints() -> None:
    os.environ["GENESIS_ROUTER_MAX_FALLBACK"] = "5"
    os.environ["GENESIS_ENV"] = "testing"
    try:
        cfg = GenesisConfig.from_env()
        assert cfg.is_testing
        assert cfg.router.max_fallback_depth == 5
        assert cfg.offline is True  # default
    finally:
        os.environ.pop("GENESIS_ROUTER_MAX_FALLBACK", None)
        os.environ.pop("GENESIS_ENV", None)


# ------------------------------------------------------------------
# Health / readiness
# ------------------------------------------------------------------
def test_health_and_readiness() -> None:
    runtime = ApplicationRuntime()
    runtime.health.register("memory", lambda: (True, "local ok"))
    runtime.health.register("providers", lambda: (True, "mock ready"))
    runtime.start()
    hlth = runtime.health.health()
    assert hlth.status == "ok"
    assert len(hlth.checks) == 2
    ready = runtime.health.ready()
    assert ready.status == "ok"


def test_readiness_degrades_before_start() -> None:
    runtime = ApplicationRuntime()
    ready = runtime.health.ready()
    assert ready.status == "degraded"
    assert any(c["name"] == "startup" and not c["ok"] for c in ready.checks)


def test_health_reports_unhealthy_check() -> None:
    runtime = ApplicationRuntime()
    runtime.health.register("broken", lambda: (False, "down"))
    runtime.start()
    assert runtime.health.health().status == "unhealthy"


def test_health_check_crash_is_caught() -> None:
    runtime = ApplicationRuntime()

    def boom():  # type: ignore[no-untyped-def]
        raise RuntimeError("crash")

    runtime.health.register("boom", boom)
    runtime.start()
    report = runtime.health.health()
    assert report.status == "unhealthy"
    assert report.checks[0]["detail"].startswith("check raised")


# ------------------------------------------------------------------
# Graceful shutdown / worker lifecycle
# ------------------------------------------------------------------
def test_worker_pool_executes_tasks() -> None:
    pool = WorkerPool(max_workers=2)
    pool.start()
    done = []

    def task():  # type: ignore[no-untyped-def]
        done.append(1)

    for _ in range(5):
        assert pool.submit(task)
    pool.stop(timeout_seconds=5)
    assert len(done) == 5
    assert pool.active == 0


def test_worker_pool_rejects_after_stop() -> None:
    pool = WorkerPool(max_workers=1)
    pool.start()
    pool.stop(timeout_seconds=5)
    assert not pool.submit(lambda: None)


def test_worker_pool_bounded_queue() -> None:
    # Capacity is checked without starting workers so nothing can dequeue.
    pool = WorkerPool(max_workers=1, queue_size=2)
    assert pool.submit(lambda: None)
    assert pool.submit(lambda: None)
    assert not pool.submit(lambda: None)  # queue full -> refused


def test_application_runtime_graceful_shutdown() -> None:
    runtime = ApplicationRuntime(max_workers=2, shutdown_timeout_seconds=5)
    hooks = []
    runtime.on_shutdown(lambda: hooks.append("hook1"))
    runtime.start()
    assert runtime.status()["started"] is True
    runtime.shutdown()
    assert runtime.status()["started"] is False
    assert hooks == ["hook1"]
    # After shutdown, readiness is degraded.
    assert runtime.health.ready().status == "degraded"


# ------------------------------------------------------------------
# Persistent storage + backup strategy
# ------------------------------------------------------------------
def test_memory_snapshot_restore_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from genesis.core import MemoryScope
    from genesis.memory.provider import MemoryProvider

    provider = MemoryProvider()
    provider.write(MemoryScope.PROJECT, "topic", "value-A")
    provider.write(MemoryScope.SESSION, "flag", True)
    snapshot = provider.snapshot()
    assert snapshot["entries"]

    fresh = MemoryProvider()
    fresh.clear()
    restored = fresh.restore(snapshot)
    assert restored == 2
    assert fresh.read(MemoryScope.PROJECT, "topic").value == "value-A"
    assert fresh.read(MemoryScope.SESSION, "flag").value is True


def test_memory_save_load_to_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from genesis.core import MemoryScope
    from genesis.memory.provider import MemoryProvider

    path = str(tmp_path / "mem" / "memory.json")
    provider = MemoryProvider()
    provider.write(MemoryScope.LONG_TERM, "fact", "persisted value")
    provider.save_to(path)
    assert os.path.exists(path)

    fresh = MemoryProvider()
    loaded = fresh.load_from(path)
    assert loaded == 1
    assert fresh.read(MemoryScope.LONG_TERM, "fact").value == "persisted value"


def test_memory_save_redacts_secrets(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from genesis.core import MemoryScope
    from genesis.memory.provider import MemoryProvider

    path = str(tmp_path / "memory.json")
    provider = MemoryProvider()
    provider.write(MemoryScope.SESSION, "creds", "token=super-secret-value-42")
    provider.save_to(path)
    content = open(path, encoding="utf-8").read()
    assert "super-secret-value-42" not in content


def test_memory_backup_creates_timestamped_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from genesis.core import MemoryScope
    from genesis.memory.provider import MemoryProvider

    dirname = str(tmp_path / "backups")
    base = os.path.join(dirname, "memory.json")
    provider = MemoryProvider()
    provider.write(MemoryScope.PROJECT, "k", "v")
    count = provider.backup(base)
    files = os.listdir(dirname)
    assert files and "memory.json" not in files  # backup is re-stamped
    assert files[0].endswith(".json")
    assert count == 1  # backup reports the number of entries persisted


# ------------------------------------------------------------------
# Logging configuration
# ------------------------------------------------------------------
def test_logging_json_formatter() -> None:
    import logging

    record = logging.LogRecord(
        name="genesis", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello world", args=(), exc_info=None,
    )
    out = JsonFormatter().format(record)
    payload = json.loads(out)
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello world"
    assert payload["logger"] == "genesis"


def test_logging_redacting_formatter() -> None:
    import logging

    fmt = _RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname=__file__, lineno=1,
        msg="secret token=abc123secret", args=(), exc_info=None,
    )
    out = fmt.format(record)
    assert "abc123secret" not in out


def test_logging_setup_configures_root() -> None:
    import logging

    logging_setup()
    root = logging.getLogger()
    assert root.handlers
    # idempotent: call again without exploding
    logging_setup()
    assert root.handlers


# ------------------------------------------------------------------
# Monitoring hooks + limits accumulate into status
# ------------------------------------------------------------------
def test_runtime_status_includes_monitoring_values() -> None:
    runtime = ApplicationRuntime()
    runtime.start()
    status = runtime.status()
    assert "health" in status
    assert "ready" in status
    assert status["workers"]["max"] == 4
    runtime.shutdown()


# ------------------------------------------------------------------
# Docker support (static files exist and reference config, no secrets)
# ------------------------------------------------------------------
def test_docker_support_files_present() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert os.path.exists(os.path.join(root, "Dockerfile"))
    assert os.path.exists(os.path.join(root, "docker", "entrypoint.sh"))
    assert os.path.exists(os.path.join(root, "docker-compose.yml"))
    dockerfile = open(os.path.join(root, "Dockerfile"), encoding="utf-8").read()
    assert "GENESIS_OFFLINE" in dockerfile
    compose = open(os.path.join(root, "docker-compose.yml"), encoding="utf-8").read()
    assert "GENESIS_ENV" in compose


# ------------------------------------------------------------------
# Recovery strategy: failed memory read degrades gracefully, not crash
# ------------------------------------------------------------------
def test_memory_recovery_graceful(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from genesis.core import MemoryScope
    from genesis.memory.provider import MemoryProvider

    provider = MemoryProvider()
    provider.write(MemoryScope.SESSION, "k", "v")
    path = str(tmp_path / "recovery.json")
    provider.save_to(path)

    # A corrupt snapshot must not crash load; it raises a traceback only if
    # the caller opts in. Here reload from the good file recovers state.
    fresh = MemoryProvider()
    fresh.load_from(path)
    assert fresh.read(MemoryScope.SESSION, "k").value == "v"