"""Provider robustness: a malformed upstream response must never escape as a
raw KeyError/IndexError/ValueError. Every case here is a regression for a
defect found by probing the real adapters with a fake transport.
"""
from __future__ import annotations

import pytest
from genesis.adapters.claude import ClaudeAdapter
from genesis.adapters.http_common import normalize_response, safe_json
from genesis.adapters.openai_compat import OpenAICompatibleAdapter
from genesis.exceptions import (
    ProviderError,
    ProviderRateLimited,
    ProviderUnavailable,
)


class _Resp:
    status_code = 200

    def __init__(self, body, *, raises=None) -> None:
        self._body = body
        self._raises = raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._body


class _StatusResp:
    def __init__(self, status: int) -> None:
        self.status_code = status

    def json(self):
        return {}


@pytest.fixture
def openai_env(monkeypatch):
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_API_KEY", "k")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_MODEL", "m")


@pytest.mark.parametrize(
    "body",
    [
        {"id": "x"},  # no choices
        {"choices": []},  # empty choices
        {"choices": [{"message": {}}]},  # no content
        {"choices": [{"message": {"content": None}}]},  # null content
        {},  # empty object
        [1, 2, 3],  # not an object
        "just a string",  # not an object
    ],
)
def test_openai_malformed_bodies_do_not_raise(openai_env, body) -> None:
    adapter = OpenAICompatibleAdapter(http_post=lambda url, **kw: _Resp(body))
    result = adapter.complete("hi")  # must not raise
    assert isinstance(result.output, str)


def test_invalid_json_is_normalized(openai_env) -> None:
    adapter = OpenAICompatibleAdapter(
        http_post=lambda url, **kw: _Resp(None, raises=ValueError("bad json"))
    )
    with pytest.raises(ProviderUnavailable):
        adapter.complete("hi")


def test_safe_json_returns_payload_or_raises_provider_error() -> None:
    assert safe_json(_Resp({"a": 1}), "p") == {"a": 1}
    with pytest.raises(ProviderError):
        safe_json(_Resp(None, raises=ValueError("x")), "p")


@pytest.mark.parametrize(
    "status,expected",
    [(429, ProviderRateLimited), (500, ProviderUnavailable), (503, ProviderUnavailable)],
)
def test_http_status_is_classified(openai_env, status, expected) -> None:
    # Regression: a 429 from a provider used to surface as ProviderUnavailable
    # instead of the retryable ProviderRateLimited.
    adapter = OpenAICompatibleAdapter(http_post=lambda url, **kw: _StatusResp(status))
    with pytest.raises(expected):
        adapter.complete("hi")


def test_error_for_status_mapping() -> None:
    from genesis.adapters.http_common import error_for_status

    assert isinstance(error_for_status("p", 429), ProviderRateLimited)
    assert isinstance(error_for_status("p", 500), ProviderUnavailable)
    assert isinstance(error_for_status("p", 404), ProviderError)
    assert error_for_status("p", 429).retryable is True


def test_normalize_response_tolerates_bad_payloads() -> None:
    for payload in [{}, {"choices": []}, {"choices": [{}]}, [1, 2], "text", None]:
        result = normalize_response("p", "m", payload, text_path="choices.0.message.content")
        assert isinstance(result.output, str)
        assert result.usage["total_tokens"] == 0


def test_claude_malformed_bodies_do_not_raise(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    bodies = [
        {"content": []},
        {},
        {"content": "not-a-list"},
        {"content": [{"type": "text"}]},
    ]
    for body in bodies:
        adapter = ClaudeAdapter(http_post=lambda url, _b=body, **kw: _Resp(_b))
        result = adapter.complete("hi")
        assert isinstance(result.output, str)
