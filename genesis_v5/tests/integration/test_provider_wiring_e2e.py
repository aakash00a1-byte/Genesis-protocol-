"""End-to-end provider wiring: a configured live provider actually routes.

Proves the previously missing link — that a configured provider reaches the
model catalog and is selected by the Kernel's router — using an injected HTTP
transport so no network or real key is involved.
"""
from __future__ import annotations

import pytest
from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.models.registry import default_registry
from genesis.providers.base import ModelCapability


class _Resp:
    status_code = 200

    def __init__(self, text: str) -> None:
        self._text = text

    def json(self):
        return {"choices": [{"message": {"content": self._text}}]}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_MODEL", "test-model")
    # Register adapters so the factory knows the openai_compat builder.
    from genesis.adapters.registration import register_default_adapters

    register_default_adapters()
    return monkeypatch


def test_unconfigured_registry_is_mock_only() -> None:
    reg = default_registry()
    assert [s.provider for s in reg.all()] == ["mock"]


def test_configured_provider_enters_the_catalog(configured) -> None:
    reg = default_registry(GenesisConfig(env=Env.TESTING, offline=False))
    providers = [s.provider for s in reg.all()]
    assert "openai_compat" in providers
    assert "mock" in providers
    # The live provider is registered ahead of the mock fallback.
    assert providers.index("openai_compat") < providers.index("mock")


def test_offline_router_still_uses_mock(configured) -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    kernel = build(cfg)
    decision = kernel.router.route(ModelCapability.CHAT, offline=True)
    assert decision.provider == "mock"


def test_online_router_selects_configured_provider(configured) -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=False)
    kernel = build(cfg)
    decision = kernel.router.route(ModelCapability.CHAT, offline=False)
    assert decision.provider == "openai_compat"
    assert decision.model == "openai_compat-default"


def test_kernel_complete_reaches_configured_provider(configured) -> None:
    # Inject the transport the adapter will use, so the real completion path
    # runs without a network call.
    import genesis.adapters.openai_compat as oc

    configured.setattr(
        oc, "default_post", lambda url, json=None, headers=None, timeout=None: _Resp("live!")
    )
    cfg = GenesisConfig(env=Env.TESTING, offline=False)
    kernel = build(cfg)
    result = kernel.complete("say hi", ModelCapability.CHAT, offline=False)
    assert result.output == "live!"
    assert result.provider == "openai_compat"
    # The key never appears in the normalized result.
    assert "test-key-not-real" not in str(result.to_dict())
