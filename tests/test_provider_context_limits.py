"""Context-window guard and failed-call reporting.

The guard must drop old history before it drops the question, skip providers
whose window cannot hold the prompt, and refuse an oversized message with real
numbers instead of walking the fallback chain and reporting a provider error.
"""

import logging

from genesis_protocol.ai.agent import GenesisAgent
from genesis_protocol.ai.failure_communicator import FailureType
from genesis_protocol.ai.provider_chain import (
    AICallResult,
    CHARS_PER_TOKEN,
    FAILURE_TOO_LARGE,
    FAILURE_UNAVAILABLE,
    ProviderChain,
)
from genesis_protocol.ai.providers.base_provider import (
    AIRequest,
    AIResponse,
    BaseProvider,
    LAST_ERROR_MAX_CHARS,
    ProviderCapability,
)


class FakeProvider(BaseProvider):
    """Provider that records what it was sent and never touches the network."""

    def __init__(self, name: str, window: int, reply: str = "ok", error=None):
        super().__init__(name)
        self.context_window = window
        self.reply = reply
        self.error = error
        self.requests = []

    async def generate(self, request: AIRequest) -> AIResponse:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return AIResponse(
            content=self.reply,
            provider=self.name,
            model=request.model,
            tokens_used=1,
            latency_ms=1,
        )

    def is_configured(self) -> bool:
        return True

    def get_capabilities(self):
        return [ProviderCapability.TEXT]

    def get_default_model(self) -> str:
        return "fake-model"


def make_chain(*providers):
    """ProviderChain with the fakes injected, no real providers constructed."""
    chain = ProviderChain.__new__(ProviderChain)
    chain._providers = {p.name: p for p in providers}
    chain._base_order = [p.name for p in providers]
    chain._request_log = []
    return chain


class FailingChain:
    """Stands in for the chain in agent tests."""

    def __init__(self, result: AICallResult, available=("groq",)):
        self._result = result
        self._available = list(available)
        self.calls = []

    def get_available_providers(self):
        return self._available

    async def call(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


# --- 1. context window handling -------------------------------------------


def test_estimate_tokens_is_conservative():
    assert ProviderChain._estimate_tokens("a" * 300) == 100
    assert ProviderChain._estimate_tokens("") == 1
    # Three chars per token, not four: the estimate must over-count.
    assert CHARS_PER_TOKEN == 3


def test_context_window_prefers_the_provider_declaration():
    chain = make_chain()
    assert chain._context_window("openrouter", FakeProvider("openrouter", 131072)) == 131072
    assert chain._context_window("freeai", FakeProvider("freeai", 32768)) == 32768
    # No declaration and not in the map -> the conservative default.
    assert chain._context_window("unknown", object()) == 32768


async def test_old_history_is_trimmed_and_the_question_is_kept():
    provider = FakeProvider("fake", window=1000)
    chain = make_chain(provider)

    messages = [{"role": "system", "content": "s" * 300}]
    for i in range(6):
        messages.append({"role": "user", "content": f"history-{i}-" + "h" * 300})
    question = "question-" + "q" * 300
    messages.append({"role": "user", "content": question})

    result = await chain.call(messages=messages, max_tokens=100, bypass_scoring=True)

    assert result.success is True
    sent = provider.requests[0].messages
    assert sent[-1]["content"] == question, "the newest message must survive intact"
    assert sent[0]["role"] == "system", "the system prompt must be kept"
    assert len(sent) < len(messages), "old history should have been dropped"
    originals = {m["content"] for m in messages}
    assert all(m["content"] in originals for m in sent), "content must never be cut"


async def test_provider_with_small_window_is_skipped():
    small = FakeProvider("small", window=1000)
    big = FakeProvider("big", window=200000)
    chain = make_chain(small, big)

    question = "q" * 30000  # ~10000 tokens
    result = await chain.call(
        messages=[{"role": "user", "content": question}],
        max_tokens=100,
        bypass_scoring=True,
    )

    assert result.success is True
    assert result.provider_used == "big"
    assert small.requests == [], "a provider that cannot hold the prompt must not be called"


async def test_oversized_message_reports_real_numbers():
    provider = FakeProvider("only", window=32768)
    chain = make_chain(provider)
    question = "q" * 594033

    result = await chain.call(
        messages=[{"role": "user", "content": question}],
        max_tokens=1000,
        bypass_scoring=True,
    )

    assert result.success is False
    assert result.failure_kind == FAILURE_TOO_LARGE
    assert "~198011 tokens" in result.error
    assert "594033 chars" in result.error
    assert "~32768 tokens" in result.error
    assert "split" in result.error.lower()
    assert provider.requests == [], "nothing should be sent when it cannot fit"


async def test_provider_errors_are_reported_as_unavailable():
    provider = FakeProvider("broken", window=200000, error=RuntimeError("boom"))
    chain = make_chain(provider)

    result = await chain.call(
        messages=[{"role": "user", "content": "hi"}], bypass_scoring=True
    )

    assert result.success is False
    assert result.failure_kind == FAILURE_UNAVAILABLE
    assert "boom" in result.error


async def test_empty_exception_text_still_names_the_failure():
    # A read timeout carries no message; the old code printed "silent: ".
    provider = FakeProvider("silent", window=200000, error=TimeoutError())
    chain = make_chain(provider)

    result = await chain.call(
        messages=[{"role": "user", "content": "hi"}], bypass_scoring=True
    )

    assert result.success is False
    assert "TimeoutError" in result.error
    assert not result.error.rstrip().endswith("silent:")


# --- 3. last_error in provider status --------------------------------------


def test_last_error_is_capped_and_credential_free():
    provider = FakeProvider("fake", window=1000)
    provider.record_failure(
        "Gemini API error: 401 key=AIzaSECRET123 Bearer sk-abcdef1234567890 "
        + "x" * 400
    )

    last_error = provider.get_status()["last_error"]
    assert last_error is not None
    assert "AIzaSECRET123" not in last_error
    assert "sk-abcdef1234567890" not in last_error
    assert len(last_error) <= LAST_ERROR_MAX_CHARS

    provider.record_success()
    assert provider.get_status()["last_error"] is None


def test_record_failure_captures_the_current_exception():
    provider = FakeProvider("fake", window=1000)
    try:
        raise ModuleNotFoundError("No module named 'aiohttp'")
    except ModuleNotFoundError:
        provider.record_failure()

    assert "ModuleNotFoundError" in provider.get_status()["last_error"]


# --- 2. agent reports the failure category --------------------------------


async def test_agent_logs_full_error_and_shows_too_large_category(caplog):
    error = (
        "Message too large: ~198011 tokens (594033 chars at 3 chars/token), "
        "but the largest available context is ~32768 tokens. "
        "Please split the message into smaller parts."
    )
    agent = GenesisAgent()
    agent.provider_chain = FailingChain(
        AICallResult(success=False, attempts=0, failure_kind=FAILURE_TOO_LARGE, error=error)
    )

    with caplog.at_level(logging.ERROR, logger="ai.agent"):
        result = await agent.process("a very long message")

    assert "Message Too Large" in result.response
    assert "Provider returned empty" not in result.response
    assert "198011" in result.response
    logged = [r.getMessage() for r in caplog.records]
    assert any("AI call failed" in m and "198011" in m for m in logged), logged


async def test_agent_reports_provider_failure_not_empty_response(caplog):
    error = "All providers failed: groq: 429 rate limit exceeded"
    agent = GenesisAgent()
    agent.provider_chain = FailingChain(
        AICallResult(success=False, attempts=3, failure_kind=FAILURE_UNAVAILABLE, error=error)
    )

    with caplog.at_level(logging.ERROR, logger="ai.agent"):
        result = await agent.process("hello")

    assert "Provider Error Encountered" in result.response
    assert "Provider returned empty" not in result.response
    assert "Response Generation Issue" not in result.response
    logged = [r.getMessage() for r in caplog.records]
    assert any("AI call failed after 3 attempt(s)" in m and "429" in m for m in logged), logged


def test_message_too_large_has_its_own_failure_type():
    from genesis_protocol.ai.failure_communicator import get_failure_communicator

    text = get_failure_communicator().communicate(
        failure_type=FailureType.MESSAGE_TOO_LARGE,
        reason="Message too large: ~198011 tokens, max ~32768 tokens. Please split.",
        attempts=["primary_provider"],
    )

    assert "Message Too Large" in text
    assert "split" in text.lower()


# --- 6. Gemini per-call timeout -------------------------------------------


class _StubResponse:
    status_code = 200

    def json(self):
        return {
            "candidates": [{
                "content": {"parts": [{"text": "hi"}], "role": "model"},
                "finishReason": "STOP",
            }],
            "usageMetadata": {"totalTokenCount": 3},
        }


class _StubClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(kwargs)
        return _StubResponse()


async def test_gemini_call_is_capped_at_15_seconds():
    from genesis_protocol.ai.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider()
    provider.api_key = "test-key"
    client = _StubClient()
    provider._get_client = lambda: client

    response = await provider.generate(
        AIRequest(messages=[{"role": "user", "content": "Hello"}],
                  model=provider.get_default_model())
    )

    assert response.content == "hi"
    assert client.calls[0]["timeout"] == 15.0

