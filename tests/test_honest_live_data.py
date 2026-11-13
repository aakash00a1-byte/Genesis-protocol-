"""Honest live-data behaviour: never fabricate when a tool fails.

Live probing showed GLUTEN inventing news, weather and prices. Two causes:

1. ``_execute_tools`` read ``result.response`` on a ``ToolResult`` that only has
   ``data``. The AttributeError was swallowed, so even a *successful* search was
   discarded and the model answered from nothing.
2. Nothing told the model that a needed tool had failed, so it filled the gap
   with invented facts, sometimes narrating a fake "*searching...*".

These tests pin the fixed contract.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestExecuteToolsReportsOutcome:
    def test_successful_tool_result_is_used(self):
        """A ToolResult carries data; it must be surfaced, not dropped."""
        from genesis_protocol.ai.agent import get_genesis_agent
        from genesis_protocol.ai.tool_system import ToolResult

        agent = get_genesis_agent()
        agent.tool_system.execute_tool = AsyncMock(
            return_value=ToolResult(True, data={"answer": "real data"})
        )

        text, failures = _run(agent._execute_tools(["web_search"], "any query"))

        assert "real data" in text
        assert failures == []

    def test_failed_tool_is_reported_as_failure(self):
        from genesis_protocol.ai.agent import get_genesis_agent
        from genesis_protocol.ai.tool_system import ToolResult

        agent = get_genesis_agent()
        agent.tool_system.execute_tool = AsyncMock(
            return_value=ToolResult(False, error="search failed")
        )

        text, failures = _run(agent._execute_tools(["web_search"], "any query"))

        assert failures, "a failed tool must be reported"
        assert "search failed" in failures[0]

    def test_success_without_data_is_a_failure(self):
        from genesis_protocol.ai.agent import get_genesis_agent
        from genesis_protocol.ai.tool_system import ToolResult

        agent = get_genesis_agent()
        agent.tool_system.execute_tool = AsyncMock(return_value=ToolResult(True, data=None))

        _, failures = _run(agent._execute_tools(["web_search"], "any query"))

        assert failures

    def test_tool_exception_is_reported(self):
        from genesis_protocol.ai.agent import get_genesis_agent

        agent = get_genesis_agent()
        agent.tool_system.execute_tool = AsyncMock(side_effect=RuntimeError("boom"))

        _, failures = _run(agent._execute_tools(["web_search"], "any query"))

        assert failures and "boom" in failures[0]


class TestLiveDataQueriesRouteToTools:
    @pytest.mark.parametrize("query", [
        "what is the latest news about AI today",
        "what is the weather in Delhi",
        "today's USD to INR exchange rate",
    ])
    def test_live_data_query_triggers_autonomous(self, query):
        """News/weather must reach autonomous mode, where tools run."""
        from genesis_protocol.ai.autonomous_mode import get_mode_manager

        assert get_mode_manager().should_use_autonomous(query) is True

    @pytest.mark.parametrize("query", [
        "what is the latest news about AI today",
        "what is the weather in Delhi",
    ])
    def test_live_data_query_detects_web_search(self, query):
        from genesis_protocol.ai.agent import get_genesis_agent

        assert "web_search" in get_genesis_agent()._detect_tool_needs(query)


class TestHonestyRuleInPrompt:
    def test_system_prompt_forbids_inventing_live_facts(self):
        from genesis_protocol.ai.agent import get_genesis_agent

        prompt = get_genesis_agent()._get_system_prompt()

        assert "HONESTY RULE" in prompt
        assert "NEVER invent live facts" in prompt
        assert "Tool failure warning" in prompt
