"""Phase 7 — Provider/Agent Integration tests.

Uses fake HTTP transports (zero network) to exercise the real adapter code
paths: health, timeout, fallback, rate-limit handling, normalized responses,
normalized errors, and the Router's capability-based selection with bounded
fallback. Providers without credentials stay DISABLED.
"""
from __future__ import annotations

import time

import pytest

from genesis.adapters.claude import ClaudeAdapter
from genesis.adapters.gemini import GeminiAdapter
from genesis.adapters.http_common import normalize_error, with_wall_clock_timeout
from genesis.adapters.local import LocalModelAdapter
from genesis.adapters.nemotron import NemotronAdapter
from genesis.adapters.openai_compat import OpenAICompatibleAdapter
from genesis.adapters.openhands import OpenHandsSDKAdapter
from genesis.core import ModelResult
from genesis.exceptions import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
    RetryLimitExceeded,
)
from genesis.models.registry import ModelRegistry, ModelSpec
from genesis.providers.base import (
    ModelCapability,
    Provider,
    ProviderCapabilities,
    ProviderHealth,
    ProviderStatus,
)
from genesis.router.router import ModelRouter


# ------------------------------------------------------------------
# Fake HTTP transport
# ------------------------------------------------------------------
class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def fake_ok_post(url, **kwargs):  # type: ignore[no-untyped-def]
    return FakeResponse(
        {
            "choices": [
                {"message": {"content": "hello from fake provider"}}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3},
        }
    )


def fake_429_post(url, **kwargs):  # type: ignore[no-untyped-def]
    raise ProviderRateLimited("rate limited", status_code=429)


def fake_500_post(url, **kwargs):  # type: ignore[no-untyped-def]
    return FakeResponse({"error": "boom"}, status_code=500)


def fake_slow_post(url, **kwargs):  # type: ignore[no-untyped-def]
    time.sleep(10)
    return FakeResponse({"choices": [{"message": {"content": "late"}}]})


# ------------------------------------------------------------------
# Adapter health (disabled when unconfigured)
# ------------------------------------------------------------------
def test_openai_compat_disabled_without_config() -> None:
    adapter = OpenAICompatibleAdapter(http_post=fake_ok_post)
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED
    with pytest.raises(ProviderUnavailable):
        adapter.complete("hello")


def test_nemotron_disabled_without_key() -> None:
    adapter = NemotronAdapter(http_post=fake_ok_post)
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED


def test_gemini_disabled_without_key() -> None:
    adapter = GeminiAdapter(http_post=fake_ok_post)
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED


def test_claude_disabled_without_key() -> None:
    adapter = ClaudeAdapter(http_post=fake_ok_post)
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED


def test_local_disabled_without_base_url() -> None:
    adapter = LocalModelAdapter(http_post=fake_ok_post)
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED


def test_openhands_disabled_without_sdk_or_key() -> None:
    adapter = OpenHandsSDKAdapter()
    assert not adapter.health().ok
    assert adapter.health().status == ProviderStatus.DISABLED


# ------------------------------------------------------------------
# Enabled adapters via injected transport + config
# ------------------------------------------------------------------
TEST_KEY_ENV = "GENESIS_TEST_FAKE_KEY"
_EXISTING = {}


def _adapter_with_key(cls, **kwargs):  # type: ignore[no-untyped-def]
    """Set a fake key BEFORE construction (adapters snapshot env at init)."""
    import os

    _EXISTING.setdefault(TEST_KEY_ENV, os.environ.get(TEST_KEY_ENV))
    os.environ[TEST_KEY_ENV] = "test-key"
    return cls(**kwargs)


def _restore_fake_key() -> None:
    import os

    previous = _EXISTING.pop(TEST_KEY_ENV, None)
    if previous is None:
        os.environ.pop(TEST_KEY_ENV, None)
    else:
        os.environ[TEST_KEY_ENV] = previous


def test_openai_compat_normalized_success() -> None:
    try:
        adapter = _adapter_with_key(
            OpenAICompatibleAdapter,
            base_url="https://fake.example/v1",
            api_key_env=TEST_KEY_ENV,
            http_post=fake_ok_post,
        )
        result = adapter.complete("hi")
        assert isinstance(result, ModelResult)
        assert result.output == "hello from fake provider"
        assert result.status == "success"
        assert result.usage["prompt_tokens"] == 5
    finally:
        _restore_fake_key()


def test_openai_compat_rate_limit_normalized() -> None:
    try:
        adapter = _adapter_with_key(
            OpenAICompatibleAdapter,
            base_url="https://fake.example/v1",
            api_key_env=TEST_KEY_ENV,
            http_post=fake_429_post,
        )
        with pytest.raises(ProviderRateLimited):
            adapter.complete("hi")
    finally:
        _restore_fake_key()


def test_openai_compat_server_error_normalized() -> None:
    try:
        adapter = _adapter_with_key(
            OpenAICompatibleAdapter,
            base_url="https://fake.example/v1",
            api_key_env=TEST_KEY_ENV,
            http_post=fake_500_post,
        )
        with pytest.raises(ProviderUnavailable):
            adapter.complete("hi")
    finally:
        _restore_fake_key()


def test_openai_compat_timeout_normalized() -> None:
    try:
        adapter = _adapter_with_key(
            OpenAICompatibleAdapter,
            base_url="https://fake.example/v1",
            api_key_env=TEST_KEY_ENV,
            http_post=fake_slow_post,
            timeout_seconds=0.2,
        )
        with pytest.raises(ProviderTimeout):
            adapter.complete("hi")
    finally:
        _restore_fake_key()


def test_wall_clock_timeout_aborts_slow_call() -> None:
    with pytest.raises(ProviderTimeout):
        with_wall_clock_timeout(lambda: time.sleep(10), 0.1, "test")


def test_wall_clock_timeout_passes_through_value() -> None:
    assert with_wall_clock_timeout(lambda: 42, 1.0, "test") == 42


# ------------------------------------------------------------------
# normalize_error mapping
# ------------------------------------------------------------------
def test_normalize_error_429() -> None:
    err = normalize_error(ProviderRateLimited("x", status_code=429), "p")
    assert isinstance(err, ProviderRateLimited)


def test_normalize_error_500() -> None:
    err = normalize_error(ProviderUnavailable("x", status_code=500), "p")
    assert isinstance(err, ProviderUnavailable)


def test_normalize_error_timeout() -> None:
    err = normalize_error(TimeoutError("timed out"), "p")
    assert isinstance(err, ProviderTimeout)


# ------------------------------------------------------------------
# Router capability selection + bounded fallback
# ------------------------------------------------------------------
class AlwaysFailProvider(Provider):
    name = "fail"

    def health(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, status=ProviderStatus.READY, ok=True)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name, models=["fail-1"])

    def complete(self, prompt, *, model=None, max_tokens=1024, temperature=0.2,
                 timeout_seconds=None) -> ModelResult:
        raise ProviderUnavailable("forced failure", provider=self.name)


def test_router_selects_by_capability() -> None:
    registry = ModelRegistry()
    registry.register(
        ModelSpec(
            name="mock-1", provider="mock",
            capabilities=[ModelCapability.CODE, ModelCapability.CHAT],
        )
    )
    from genesis.providers.mock import MockProvider

    router = ModelRouter(
        registry,
        factory=lambda name: MockProvider(),
        default_provider="mock",
        max_fallback_depth=3,
    )
    decision = router.route(ModelCapability.CODE, offline=True)
    assert decision.model == "mock-1"
    assert decision.provider == "mock"


def test_router_fallback_chain() -> None:
    registry = ModelRegistry()
    registry.register(
        ModelSpec(name="fail-1", provider="fail",
                  capabilities=[ModelCapability.CHAT])
    )
    registry.register(
        ModelSpec(name="mock-1", provider="mock",
                  capabilities=[ModelCapability.CHAT])
    )
    from genesis.providers.mock import MockProvider

    def factory(name):  # type: ignore[no-untyped-def]
        return AlwaysFailProvider() if name == "fail" else MockProvider()

    router = ModelRouter(registry, factory, default_provider="fail",
                         max_fallback_depth=3)
    result = router.complete("hi", ModelCapability.CHAT, offline=False)
    assert result.status == "fallback"
    assert result.provider == "mock"


def test_router_exhausts_fallback_without_infinite_loop() -> None:
    registry = ModelRegistry()
    for i in range(5):
        registry.register(
            ModelSpec(name=f"fail-{i}", provider="fail",
                      capabilities=[ModelCapability.CHAT])
        )
    router = ModelRouter(
        registry,
        factory=lambda name: AlwaysFailProvider(),
        default_provider="fail",
        max_fallback_depth=3,
    )
    with pytest.raises(RetryLimitExceeded):
        router.complete("hi", ModelCapability.CHAT, offline=False)


def test_router_offline_filters_non_offline_providers() -> None:
    registry = ModelRegistry()
    registry.register(
        ModelSpec(name="mock-1", provider="mock",
                  capabilities=[ModelCapability.CHAT])
    )
    registry.register(
        ModelSpec(name="remote-1", provider="openai_compat",
                  capabilities=[ModelCapability.CHAT])
    )
    from genesis.providers.mock import MockProvider

    router = ModelRouter(
        registry,
        factory=lambda name: MockProvider(),
        default_provider="mock",
        max_fallback_depth=3,
    )
    decision = router.route(ModelCapability.CHAT, offline=True)
    assert decision.model == "mock-1"


# ------------------------------------------------------------------
# Provider health aggregation (all adapters report, none fabricate)
# ------------------------------------------------------------------
def test_all_adapters_report_health_without_credentials() -> None:
    from genesis.adapters.registration import register_default_adapters
    from genesis.providers.factory import get_factory

    register_default_adapters()
    factory = get_factory()
    names = factory.names()
    assert "mock" in names
    assert "openhandssdk" in names
    assert "nemotron" in names
    assert "openai_compat" in names
    assert "gemini" in names
    assert "claude" in names
    assert "local" in names
    # Without credentials, all non-mock adapters are DISABLED (never ok).
    for name in names:
        health = factory.health(name)
        if name == "mock":
            assert health.ok
        else:
            assert not health.ok
            assert health.status == ProviderStatus.DISABLED