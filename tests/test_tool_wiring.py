"""The tool-first path must actually run the tools it claims to run.

Three gaps were found by probing the live deployment:

* ``code_execution`` was called with empty parameters, so it could only ever
  fail with "No code provided";
* ``memory_store`` was never selected (every "remember" became a recall) and it
  wrote to a global bucket (``user_id=0``);
* ``memory_recall`` read that same global bucket.

These tests pin the fixed behaviour, including the per-user isolation.
"""
import os
import tempfile

import pytest

os.environ.setdefault("GLUTEN_MEMORY_DB", os.path.join(tempfile.gettempdir(), "gluten_test_mem.db"))


def _agent():
    from genesis_protocol.ai.agent import get_genesis_agent

    return get_genesis_agent()


class TestCodeExtraction:
    def test_arithmetic_expression_becomes_code(self):
        code = _agent()._extract_code("calculate 17*23 using python")
        assert code == "print(17*23)"

    def test_what_is_expression(self):
        assert _agent()._extract_code("what is 2+2") == "print(2+2)"

    def test_caret_becomes_power(self):
        assert _agent()._extract_code("calculate 2^10") == "print(2**10)"

    def test_fenced_block_is_extracted(self):
        code = _agent()._extract_code("run this\n```python\nprint(1)\n```")
        assert code == "print(1)"

    def test_plain_prose_is_not_code(self):
        assert _agent()._extract_code("run python code to print the first 5 primes") == ""
        assert _agent()._extract_code("how do I run a marathon") == ""
        assert _agent()._extract_code("what is the capital of France") == ""

    def test_code_execution_only_triggers_with_code(self):
        agent = _agent()
        assert "code_execution" in agent._detect_tool_needs("calculate 17*23")
        assert "code_execution" not in agent._detect_tool_needs("how do I run a marathon")


class TestCodeExecutionRuns:
    def test_calculate_produces_output(self):
        import asyncio

        agent = _agent()
        query = "calculate 17*23"
        text, failures = asyncio.run(agent._execute_tools(["code_execution"], query))
        assert failures == []
        assert "391" in text

    def test_fenced_block_runs(self):
        import asyncio

        agent = _agent()
        query = "run\n```python\nprint(sum(range(1,11)))\n```"
        text, failures = asyncio.run(agent._execute_tools(["code_execution"], query))
        assert failures == []
        assert "55" in text


class TestMemoryIsPerUser:
    def test_remember_selects_store_not_recall(self):
        agent = _agent()
        tools = agent._detect_tool_needs("remember that my name is Aakash")
        assert "memory_store" in tools
        assert "memory_recall" not in tools

    def test_past_question_selects_recall(self):
        assert "memory_recall" in _agent()._detect_tool_needs("do you remember my name")

    def test_store_then_recall_same_user(self):
        import asyncio

        from genesis_protocol.agentic.memory import get_agent_memory

        agent = _agent()
        user_id = 4242
        store_q = "remember that my favourite colour is teal"
        asyncio.run(agent._execute_tools(["memory_store"], store_q, user_id))
        text, failures = asyncio.run(
            agent._execute_tools(["memory_recall"], "favourite colour", user_id)
        )
        assert failures == []
        assert "teal" in text
        get_agent_memory().forget(user_id, get_agent_memory().list_memories(user_id)[0]["id"])

    def test_other_user_cannot_see_memories(self):
        import asyncio

        agent = _agent()
        asyncio.run(agent._execute_tools(
            ["memory_store"], "remember that my secret is quokka", 5151
        ))
        text, _ = asyncio.run(agent._execute_tools(["memory_recall"], "secret", 6262))
        assert "quokka" not in text

    def test_store_without_user_id_is_refused(self):
        import asyncio

        from genesis_protocol.ai.tool_system import get_tool_system

        result = asyncio.run(
            get_tool_system().execute_tool("memory_store", {"key": "k", "value": "v"})
        )
        assert result.success is False
        assert "user id" in (result.error or "")
