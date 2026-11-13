"""Key-free search fallback, and the web_search tool that uses it.

The web_search tool used to import ``TavilyIntegration``, a name that does not
exist, so every call raised ImportError and no search ever ran. The tool now
uses ``TavilyClient`` when configured and falls back to key-free providers.
Network calls are faked here so the tests are deterministic.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeResponse:
    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload or {}

    def json(self):
        return self._payload


class TestKeyFreeParsing:
    def test_duckduckgo_html_is_parsed_and_urls_unwrapped(self):
        from genesis_protocol.integrations.key_free_search import KeyFreeSearch

        html = (
            '<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fx">'
            'Example Title</a>'
            '<a class="result__snippet" href="#">Snippet text</a>'
            '</div></div></div>'
        )
        search = KeyFreeSearch()
        search._client.post = AsyncMock(return_value=_FakeResponse(text=html))

        results = _run(search._search_duckduckgo("q", 5))

        assert results[0]["title"] == "Example Title"
        assert results[0]["url"] == "https://example.com/x"
        assert results[0]["content"] == "Snippet text"

    def test_google_news_rss_is_parsed(self):
        from genesis_protocol.integrations.key_free_search import KeyFreeSearch

        rss = (
            "<item><title>Headline One</title><link>https://n.example/1</link>"
            "<pubDate>Fri, 13 Nov 2026 00:00:00 GMT</pubDate></item>"
        )
        search = KeyFreeSearch()
        search._client.get = AsyncMock(return_value=_FakeResponse(text=rss))

        results = _run(search._search_google_news("q", 5))

        assert results[0]["title"] == "Headline One"
        assert results[0]["url"] == "https://n.example/1"

    def test_search_returns_first_provider_with_results(self):
        from genesis_protocol.integrations import key_free_search as kfs

        search = kfs.KeyFreeSearch()
        search._search_duckduckgo = AsyncMock(return_value=[{"title": "t", "url": "u", "content": "c"}])
        search._search_wikipedia = AsyncMock(return_value=[])

        out = _run(search.search("some query"))

        assert out["source"] == "duckduckgo"
        assert out["results"]
        search._search_wikipedia.assert_not_called()

    def test_search_reports_error_when_all_providers_fail(self):
        from genesis_protocol.integrations import key_free_search as kfs

        search = kfs.KeyFreeSearch()
        search._search_duckduckgo = AsyncMock(side_effect=RuntimeError("blocked"))
        search._search_wikipedia = AsyncMock(side_effect=RuntimeError("blocked"))

        out = _run(search.search("some query"))

        assert out["results"] == []
        assert "blocked" in out["error"]


class TestWebSearchTool:
    def _tool(self):
        from genesis_protocol.ai.tool_system import get_tool_system
        return get_tool_system()

    def test_uses_key_free_fallback_when_tavily_unconfigured(self):
        ts = self._tool()
        with patch(
            "genesis_protocol.integrations.tavily_integration.TavilyClient.is_configured",
            return_value=False,
        ), patch(
            "genesis_protocol.integrations.key_free_search.get_key_free_search"
        ) as mock_get:
            mock_get.return_value.search = AsyncMock(return_value={
                "results": [{"title": "T", "url": "u", "content": "c"}],
                "source": "duckduckgo",
            })
            result = _run(ts.execute_tool("web_search", {"query": "hello"}))

        assert result.success is True
        assert result.data["source"] == "duckduckgo"
        assert result.data["results"]

    def test_reports_failure_when_everything_fails(self):
        ts = self._tool()
        with patch(
            "genesis_protocol.integrations.tavily_integration.TavilyClient.is_configured",
            return_value=False,
        ), patch(
            "genesis_protocol.integrations.key_free_search.get_key_free_search"
        ) as mock_get:
            mock_get.return_value.search = AsyncMock(
                return_value={"results": [], "error": "all providers down"}
            )
            result = _run(ts.execute_tool("web_search", {"query": "hello"}))

        assert result.success is False
        assert "all providers down" in result.error

    def test_empty_query_is_rejected(self):
        ts = self._tool()
        result = _run(ts.execute_tool("web_search", {"query": ""}))

        assert result.success is False
        assert "No query" in result.error
