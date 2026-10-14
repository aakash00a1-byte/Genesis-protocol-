"""Phase 4 — Memory Fabric tests.

Covers: read, write, scope, relevance, duplicate, conflict, failure,
sanitization, policy, and Kernel integration.
"""
from __future__ import annotations

import pytest

from genesis.config.settings import MemoryConfig
from genesis.core import (
    MemoryEntry,
    MemoryScope,
    MemoryWritePolicy,
)
from genesis.exceptions import MemoryError_
from genesis.memory.adapter import ProviderMemoryAdapter
from genesis.memory.mempalace import (
    MemPalaceAdapter,
    MemPalaceMock,
    create_mempalace_adapter,
)
from genesis.memory.provider import MemoryProvider


@pytest.fixture
def provider() -> MemoryProvider:
    return MemoryProvider()


# ------------------------------------------------------------------
# read / write
# ------------------------------------------------------------------
def test_write_and_read(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.SESSION, "greeting", "hello")
    entry = provider.read(MemoryScope.SESSION, "greeting")
    assert entry is not None
    assert entry.value == "hello"
    assert entry.scope == MemoryScope.SESSION


def test_read_missing_returns_none(provider: MemoryProvider) -> None:
    assert provider.read(MemoryScope.SESSION, "nope") is None


def test_write_returns_entry_with_metadata(provider: MemoryProvider) -> None:
    entry = provider.write(
        MemoryScope.TASK,
        "k",
        {"a": 1},
        metadata={"source": "test"},
    )
    assert isinstance(entry, MemoryEntry)
    assert entry.metadata["source"] == "test"


# ------------------------------------------------------------------
# scope isolation
# ------------------------------------------------------------------
def test_scope_isolation(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.SESSION, "key", "session-value")
    provider.write(MemoryScope.PROJECT, "key", "project-value")
    assert provider.read(MemoryScope.SESSION, "key").value == "session-value"
    assert provider.read(MemoryScope.PROJECT, "key").value == "project-value"
    # Same key in different scopes are distinct.
    assert provider.read(MemoryScope.TASK, "key") is None


def test_list_scope(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.TASK, "a", 1)
    provider.write(MemoryScope.TASK, "b", 2)
    provider.write(MemoryScope.SESSION, "c", 3)
    task_entries = provider.list_scope(MemoryScope.TASK)
    assert {e.key for e in task_entries} == {"a", "b"}


# ------------------------------------------------------------------
# relevance filtering
# ------------------------------------------------------------------
def test_relevance_search_orders_by_relevance(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.PROJECT, "auth", "authentication token handling")
    provider.write(MemoryScope.PROJECT, "db", "database schema migration")
    provider.write(MemoryScope.PROJECT, "unrelated", "the weather today")
    hits = provider.search("authentication token", scopes=[MemoryScope.PROJECT])
    assert hits[0].key == "auth"
    assert hits[0].value == "authentication token handling"


def test_relevance_search_respects_scope_filter(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.SESSION, "s", "python code review")
    provider.write(MemoryScope.PROJECT, "p", "python code review")
    hits = provider.search("python", scopes=[MemoryScope.SESSION])
    assert [h.key for h in hits] == ["s"]


def test_relevance_search_top_k(provider: MemoryProvider) -> None:
    for i in range(10):
        provider.write(MemoryScope.PROJECT, f"k{i}", f"shared topic value {i}")
    hits = provider.search("shared topic", scopes=[MemoryScope.PROJECT], top_k=3)
    assert len(hits) == 3


# ------------------------------------------------------------------
# duplicate handling
# ------------------------------------------------------------------
def test_duplicate_key_updates_in_place(provider: MemoryProvider) -> None:
    first = provider.write(MemoryScope.SESSION, "k", "v1")
    version_before = first.version
    second = provider.write(MemoryScope.SESSION, "k", "v1")
    entries = provider.list_scope(MemoryScope.SESSION)
    assert len(entries) == 1
    assert second.version == version_before + 1


# ------------------------------------------------------------------
# conflict handling
# ------------------------------------------------------------------
def test_conflicting_values_recorded_not_lost(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.SESSION, "k", "original")
    entry = provider.write(MemoryScope.SESSION, "k", "different")
    # Original value preserved (no data loss).
    assert entry.value == "original"
    conflicts = entry.metadata.get("conflicts", [])
    assert len(conflicts) == 1
    assert "different" in conflicts[0]["incoming"]


# ------------------------------------------------------------------
# graceful failure
# ------------------------------------------------------------------
def test_graceful_failure_returns_error(provider: MemoryProvider) -> None:
    provider.set_failure(True)
    with pytest.raises(MemoryError_):
        provider.read(MemoryScope.SESSION, "k")


def test_non_graceful_failure_raises() -> None:
    cfg = MemoryConfig(graceful_failure=False)
    provider = MemoryProvider(cfg)
    provider.set_failure(True)
    with pytest.raises(MemoryError_):
        provider.search("anything")


def test_failure_recovers(provider: MemoryProvider) -> None:
    provider.set_failure(True)
    with pytest.raises(MemoryError_):
        provider.read(MemoryScope.SESSION, "k")
    provider.set_failure(False)
    provider.write(MemoryScope.SESSION, "k", "ok")
    assert provider.read(MemoryScope.SESSION, "k").value == "ok"


# ------------------------------------------------------------------
# secret sanitization
# ------------------------------------------------------------------
def test_secret_sanitization_on_write(provider: MemoryProvider) -> None:
    entry = provider.write(
        MemoryScope.SESSION, "creds", "api_key=sk-1234567890abcdef"
    )
    assert "sk-1234567890abcdef" not in str(entry.value)
    assert entry.secret_redacted is True


def test_sanitization_can_be_disabled() -> None:
    provider = MemoryProvider(MemoryConfig(redact_secrets=False))
    entry = provider.write(MemoryScope.SESSION, "creds", "api_key=sk-1234567890abcdef")
    assert "sk-1234567890abcdef" in str(entry.value)


# ------------------------------------------------------------------
# write policy
# ------------------------------------------------------------------
def test_policy_never_denies_write(provider: MemoryProvider) -> None:
    with pytest.raises(MemoryError_):
        provider.write(
            MemoryScope.SESSION, "k", "v", policy=MemoryWritePolicy.NEVER
        )
    assert provider.read(MemoryScope.SESSION, "k") is None


def test_policy_verified_requires_verified(provider: MemoryProvider) -> None:
    with pytest.raises(MemoryError_):
        provider.write(
            MemoryScope.SESSION,
            "k",
            "v",
            policy=MemoryWritePolicy.VERIFIED,
            verified=False,
        )
    entry = provider.write(
        MemoryScope.SESSION,
        "k",
        "v",
        policy=MemoryWritePolicy.VERIFIED,
        verified=True,
    )
    assert entry.value == "v"


def test_policy_on_failure(provider: MemoryProvider) -> None:
    # ON_FAILURE writes only when not verified.
    with pytest.raises(MemoryError_):
        provider.write(
            MemoryScope.SESSION,
            "k",
            "v",
            policy=MemoryWritePolicy.ON_FAILURE,
            verified=True,
        )
    entry = provider.write(
        MemoryScope.SESSION,
        "k",
        "v",
        policy=MemoryWritePolicy.ON_FAILURE,
        verified=False,
    )
    assert entry.value == "v"


# ------------------------------------------------------------------
# audit trail
# ------------------------------------------------------------------
def test_audit_trail_records_operations(provider: MemoryProvider) -> None:
    provider.write(MemoryScope.SESSION, "k", "v")
    provider.read(MemoryScope.SESSION, "k")
    types = {e.event_type for e in provider.audit_trail()}
    assert "memory_write" in types
    assert "memory_read" in types


# ------------------------------------------------------------------
# MemPalace adapter boundary
# ------------------------------------------------------------------
def test_mempalace_unconfigured_returns_mock() -> None:
    adapter = create_mempalace_adapter(MemoryConfig())
    assert isinstance(adapter, MemPalaceMock)


def test_mempalace_mock_put_get() -> None:
    mock = MemPalaceMock()
    mock.put("project", "k", "v")
    assert mock.get("project", "k")["value"] == "v"


def test_mempalace_mock_query_relevance() -> None:
    mock = MemPalaceMock()
    mock.put("project", "auth", "authentication token handling")
    mock.put("project", "db", "database schema")
    results = mock.query("authentication token")
    assert results[0]["key"] == "auth"


def test_mempalace_adapter_requires_configuration() -> None:
    # Without endpoint + key the real adapter refuses to initialize.
    with pytest.raises(MemoryError_):
        MemPalaceAdapter(MemoryConfig())


def test_provider_adapter_unreachable_backend_raises() -> None:
    class DeadBackend:
        def health(self) -> bool:
            return False

        def write(self, entry):  # pragma: no cover
            raise AssertionError("should not be called")

        def read(self, scope, key):  # pragma: no cover
            raise AssertionError("should not be called")

        def search(self, query, scopes, top_k):  # pragma: no cover
            raise AssertionError("should not be called")

    adapter = ProviderMemoryAdapter(DeadBackend())
    with pytest.raises(MemoryError_):
        adapter.write(MemoryScope.SESSION, "k", "v")


# ------------------------------------------------------------------
# Kernel integration
# ------------------------------------------------------------------
def test_kernel_memory_integration() -> None:
    from genesis.bootstrap import build

    kernel = build()
    entry = kernel.memory_write(MemoryScope.PROJECT, "fact", "genesis is offline")
    assert kernel.memory_read(MemoryScope.PROJECT, "fact").value == "genesis is offline"
    hits = kernel.memory_search("genesis offline", scopes=[MemoryScope.PROJECT])
    assert any(h.key == "fact" for h in hits)
    assert entry.entry_id


def test_kernel_run_writes_memory() -> None:
    from genesis.bootstrap import build
    from genesis.kernel.kernel import KernelRequest

    kernel = build()
    resp = kernel.run(KernelRequest(task="implement a hello function"))
    assert resp.ok
    # The run writes a task-scoped memory entry.
    entries = kernel.memory.list_scope(MemoryScope.TASK)
    assert len(entries) >= 1
    assert resp.audit_ids