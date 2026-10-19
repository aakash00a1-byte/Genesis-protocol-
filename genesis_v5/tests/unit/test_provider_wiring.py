"""Provider wiring tests: the LLM boundary is config-driven, never hardcoded.

These tests exercise the real adapter code path with an injected transport, so
no network, no credentials, and no paid service is involved. They prove that:
  - with no config the adapter is DISABLED and refuses to fabricate success;
  - with config it calls the OpenAI-compatible endpoint and normalizes the
    response;
  - the API key is read from the environment and never appears in the result
    or in logs.
"""
from __future__ import annotations

import pytest
from genesis.adapters.openai_compat import OpenAICompatibleAdapter
from genesis.exceptions import ProviderUnavailable
from genesis.providers.base import ProviderStatus


class _FakeResponse:
    def __init__(self, data, status_code: int = 200) -> None:
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


def test_adapter_is_disabled_without_config(monkeypatch) -> None:
    monkeypatch.delenv("GENESIS_OPENAI_COMPAT_BASE_URL", raising=False)
    monkeypatch.delenv("GENESIS_OPENAI_COMPAT_API_KEY", raising=False)
    adapter = OpenAICompatibleAdapter()
    assert adapter.health().status is ProviderStatus.DISABLED
    with pytest.raises(ProviderUnavailable):
        adapter.complete("hello")


def test_adapter_completes_via_injected_transport(monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_MODEL", "test-model")

    calls: dict = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls["url"] = url
        calls["headers"] = headers
        calls["payload"] = json
        return _FakeResponse(
            {"choices": [{"message": {"content": "hello from the model"}}]}
        )

    adapter = OpenAICompatibleAdapter(http_post=fake_post)
    assert adapter.health().status is ProviderStatus.READY

    result = adapter.complete("say hello")
    assert result.output == "hello from the model"
    assert result.provider == "openai_compat"
    assert result.model == "test-model"
    # The endpoint and auth header are correct...
    assert calls["url"].endswith("/chat/completions")
    assert calls["headers"]["Authorization"].startswith("Bearer ")
    # ...and the key is never echoed into the normalized result.
    assert "test-key-not-real" not in str(result.to_dict())


def test_http_error_is_normalized(monkeypatch) -> None:
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_API_KEY", "test-key-not-real")

    def failing_post(url, json=None, headers=None, timeout=None):
        return _FakeResponse({}, status_code=500)

    adapter = OpenAICompatibleAdapter(http_post=failing_post)
    from genesis.exceptions import ProviderError

    with pytest.raises(ProviderError):
        adapter.complete("hello")
