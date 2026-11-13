"""Source credibility labels and exact live facts (weather, FX).

Finding a headline is not confirming it: a wire-service press release is not
independent reporting. These tests pin the labels, the tool wiring and the
parameter extraction that feeds the exact, key-free weather/FX providers.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestSourceCredibility:
    def test_recognised_newsroom_is_verified(self):
        from genesis_protocol.integrations.source_credibility import classify

        assert classify("AI boom", "https://www.reuters.com/tech/x")["label"] == "verified"

    def test_wire_press_release_is_promotional(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("AlphaPepe Reveals New DEX", "https://www.globenewswire.com/news-release/x")
        assert out["label"] == "promotional-unverified"
        assert "press release" in out["reason"]

    def test_sponsored_marker_is_promotional(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("Sponsored: buy now", "https://example.com/p")
        assert out["label"] == "promotional-unverified"
        assert "sponsored" in out["reason"]

    def test_unknown_source_is_developing(self):
        from genesis_protocol.integrations.source_credibility import classify

        assert classify("Some claim", "https://randomblog.xyz/p")["label"] == "developing"

    def test_missing_url_is_developing(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("Some claim", "")
        assert out["label"] == "developing"
        assert "no source URL" in out["reason"]

    def test_overall_prefers_verified(self):
        from genesis_protocol.integrations.source_credibility import assess, overall

        labelled = assess([
            {"title": "t", "url": "https://randomblog.xyz/p"},
            {"title": "t", "url": "https://www.bbc.com/news/x"},
        ])
        assert overall(labelled) == "verified"

    def test_overall_is_promotional_when_all_are(self):
        from genesis_protocol.integrations.source_credibility import assess, overall

        labelled = assess([
            {"title": "t", "url": "https://www.prnewswire.com/x"},
            {"title": "t", "url": "https://www.globenewswire.com/y"},
        ])
        assert overall(labelled) == "promotional-unverified"

    def test_format_includes_label_domain_and_url(self):
        from genesis_protocol.integrations.source_credibility import assess, format_for_model

        text = format_for_model(assess([{"title": "T", "url": "https://www.reuters.com/x", "content": "c"}]))
        assert "[verified]" in text
        assert "reuters.com" in text
        assert "https://www.reuters.com/x" in text


class TestPublisherAttribution:
    """Google News links point at news.google.com; the title names the source."""

    def test_trusted_publisher_name_is_verified(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("AI boom continues", "https://news.google.com/rss/articles/x",
                       publisher="Reuters")
        assert out["label"] == "verified"
        assert out["domain"] == "reuters.com"

    def test_unknown_publisher_is_developing_and_named(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("Some claim", "https://news.google.com/rss/articles/x",
                       publisher="Tiny Blog")
        assert out["label"] == "developing"
        assert "tiny blog" in out["reason"]

    def test_aggregator_page_without_publisher_is_developing(self):
        from genesis_protocol.integrations.source_credibility import classify

        out = classify("AI News - Latest", "https://news.google.com/topics/x")
        assert out["label"] == "developing"
        assert "aggregator" in out["reason"]

    def test_assess_uses_publisher(self):
        from genesis_protocol.integrations.source_credibility import assess, overall

        labelled = assess([
            {"title": "T", "url": "https://news.google.com/rss/articles/x",
             "publisher": "BBC News"},
        ])
        assert labelled[0]["label"] == "verified"
        assert overall(labelled) == "verified"


class TestLiveFacts:
    def test_weather_returns_exact_value(self):
        from genesis_protocol.integrations import live_facts

        payload = {"current_condition": [{
            "temp_C": "24", "FeelsLikeC": "26", "humidity": "55",
            "weatherDesc": [{"value": "Haze"}], "observation_time": "03:59 PM",
        }], "nearest_area": [{"areaName": [{"value": "Delhi"}]}]}

        class _Resp:
            status_code = 200
            def json(self): return payload

        with patch.object(live_facts.httpx, "AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=_Resp())
            out = _run(live_facts.get_weather("Delhi"))

        assert out["temperature_c"] == "24"
        assert out["location"] == "Delhi"
        assert out["source"] == "wttr.in"

    def test_fx_returns_exact_value(self):
        from genesis_protocol.integrations import live_facts

        class _Resp:
            status_code = 200
            def json(self): return {"rates": {"INR": 94.25}, "date": "2026-11-13"}

        with patch.object(live_facts.httpx, "AsyncClient") as client_cls:
            client = client_cls.return_value.__aenter__.return_value
            client.get = AsyncMock(return_value=_Resp())
            out = _run(live_facts.get_exchange_rate("USD", "INR"))

        assert out["rate"] == 94.25
        assert out["rate_date"] == "2026-11-13"

    def test_weather_without_location_errors(self):
        from genesis_protocol.integrations.live_facts import get_weather

        assert "error" in _run(get_weather(""))

    def test_fx_without_currencies_errors(self):
        from genesis_protocol.integrations.live_facts import get_exchange_rate

        assert "error" in _run(get_exchange_rate("", "INR"))


class TestToolWiring:
    def test_weather_and_fx_tools_are_registered(self):
        from genesis_protocol.ai.tool_system import get_tool_system

        tools = get_tool_system().tools
        assert "get_weather" in tools
        assert "get_exchange_rate" in tools

    def test_web_search_labels_results(self):
        from genesis_protocol.ai.tool_system import get_tool_system

        with patch(
            "genesis_protocol.integrations.tavily_integration.TavilyClient.is_configured",
            return_value=False,
        ), patch(
            "genesis_protocol.integrations.key_free_search.get_key_free_search"
        ) as mock_get:
            mock_get.return_value.search = AsyncMock(return_value={
                "results": [{"title": "T", "url": "https://www.reuters.com/x", "content": "c"}],
                "source": "duckduckgo",
            })
            result = _run(get_tool_system().execute_tool("web_search", {"query": "q"}))

        assert result.data["results"][0]["label"] == "verified"


class TestParamExtraction:
    def _agent(self):
        from genesis_protocol.ai.agent import get_genesis_agent
        return get_genesis_agent()

    @pytest.mark.parametrize("query,expected", [
        ("what is the weather in Delhi", "Delhi"),
        ("Mumbai ka mausam kaisa hai", "Mumbai"),
    ])
    def test_weather_location_extracted(self, query, expected):
        agent = self._agent()
        assert agent._build_tool_params("get_weather", query)["location"] == expected

    @pytest.mark.parametrize("query,base,quote", [
        ("USD to INR exchange rate", "USD", "INR"),
        ("convert 100 usd to inr", "USD", "INR"),
        ("dollar to rupee rate", "USD", "INR"),
    ])
    def test_currency_pair_extracted(self, query, base, quote):
        agent = self._agent()
        params = agent._build_tool_params("get_exchange_rate", query)
        assert (params["base"], params["quote"]) == (base, quote)

    def test_weather_query_routes_to_weather_not_search(self):
        agent = self._agent()
        tools = agent._detect_tool_needs("what is the weather in Delhi")
        assert "get_weather" in tools
        assert "web_search" not in tools

    def test_news_query_still_routes_to_search(self):
        agent = self._agent()
        assert "web_search" in agent._detect_tool_needs("latest AI news")


class TestCitationRulesInPrompt:
    def test_prompt_requires_citation_and_labels(self):
        from genesis_protocol.ai.agent import get_genesis_agent

        prompt = get_genesis_agent()._get_system_prompt()
        assert "CITATION & SOURCE-QUALITY RULES" in prompt
        assert "promotional" in prompt
        assert "never\n  invent a URL" in prompt
