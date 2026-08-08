"""Tests for v1.6 Tool Ecosystem"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestToolRegistry:
    def test_get_tools(self):
        from genesis_protocol.tools import get_tool_registry
        registry = get_tool_registry()
        tools = registry.get_all_tools()
        assert len(tools) >= 8

    def test_calculator(self):
        from genesis_protocol.tools import get_tool_registry
        registry = get_tool_registry()
        result = registry.execute("calculator", {"expression": "2+2"})
        assert result["success"] is True
        assert result["result"] == 4

    def test_notes(self):
        from genesis_protocol.tools import get_tool_registry
        registry = get_tool_registry()
        result = registry.execute("notes", {"action": "save", "key": "test", "content": "Hello"})
        assert result["success"] is True
        result = registry.execute("notes", {"action": "get", "key": "test"})
        assert result["success"] is True
        assert result["note"]["content"] == "Hello"


class TestToolChains:
    def test_get_chains(self):
        from genesis_protocol.tools import get_chain_executor
        executor = get_chain_executor()
        chains = executor.get_all_chains()
        assert len(chains) >= 3


class TestToolStats:
    def test_record_usage(self):
        from genesis_protocol.tools import get_tool_stats
        stats = get_tool_stats()
        stats.record_usage("calculator", True, 10.5)
        stats_dict = stats.get_tool_stats("calculator")
        assert stats_dict["tool"] == "calculator"


class TestToolRecommender:
    def test_recommend_calculator(self):
        from genesis_protocol.tools import get_tool_recommender
        recommender = get_tool_recommender()
        recs = recommender.recommend("Calculate 2+2")
        assert len(recs) > 0
        assert any(r.tool_name == "calculator" for r in recs)

    def test_suggestion(self):
        from genesis_protocol.tools import get_tool_recommender
        recommender = get_tool_recommender()
        suggestion = recommender.get_suggestion("What is Python?")
        assert "web_search" in suggestion or len(suggestion) > 0
