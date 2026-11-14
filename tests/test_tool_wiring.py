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

    def test_arithmetic_uses_safe_calculator_not_code_execution(self):
        # "calculate 17*23" used to route to the restricted code_execution tool,
        # so a non-owner got a denial and the model answered 437 from memory.
        agent = _agent()
        needs = agent._detect_tool_needs("calculate 17*23")
        assert "calculator" in needs
        assert "code_execution" not in needs
        assert "code_execution" not in agent._detect_tool_needs("how do I run a marathon")

    def test_fenced_block_still_uses_code_execution(self):
        agent = _agent()
        assert "code_execution" in agent._detect_tool_needs("run\n```python\nprint(1)\n```")


class TestCodeExecutionRuns:
    # Code execution is a restricted tool, so these exercise the owner path
    # (chat authorizes each tool by its registry permission now).
    _OWNER = 1

    @pytest.fixture(autouse=True)
    def _owner(self, monkeypatch):
        monkeypatch.setenv("GLUTEN_OWNER_IDS", str(self._OWNER))
        import genesis_protocol.agentic.policy as policy

        policy._default = None

    def test_calculate_produces_output(self):
        import asyncio

        agent = _agent()
        query = "calculate 17*23"
        text, failures = asyncio.run(
            agent._execute_tools(["code_execution"], query, user_id=self._OWNER)
        )
        assert failures == []
        assert "391" in text

    def test_fenced_block_runs(self):
        import asyncio

        agent = _agent()
        query = "run\n```python\nprint(sum(range(1,11)))\n```"
        text, failures = asyncio.run(
            agent._execute_tools(["code_execution"], query, user_id=self._OWNER)
        )
        assert failures == []
        assert "55" in text


class TestArithmeticIsCorrectForEveryone:
    """A non-owner must still get the right arithmetic answer, via the safe
    calculator, without reaching code execution.
    """

    def test_non_owner_arithmetic_is_correct(self):
        import asyncio

        agent = _agent()
        text, failures = asyncio.run(
            agent._execute_tools(["calculator"], "calculate 17*23", user_id=2)
        )
        assert failures == []
        assert "391" in text

    def test_non_owner_code_execution_is_denied(self):
        import asyncio

        agent = _agent()
        text, failures = asyncio.run(
            agent._execute_tools(["code_execution"], "run\n```python\nprint(1)\n```", user_id=2)
        )
        assert any("code_execution" in f for f in failures)


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


class TestAgentLoopDoesNotFakeCompletion:
    """``/api/agent/run`` used to return 'completed' with zero steps."""

    def _loop(self):
        from genesis_protocol.agentic.agent_loop import AgentLoop

        return AgentLoop()

    def test_goal_with_expression_runs_calculator(self):
        result = self._loop().run(user_id=1, goal="calculate 12+30")
        assert result["state"] == "completed"
        tools = [s for s in result["steps"] if s["type"] == "tool"]
        assert tools and tools[0]["tool"] == "calculator"
        assert tools[0]["result"]["result"] == 42

    def test_unplannable_goal_reports_no_plan(self):
        result = self._loop().run(user_id=1, goal="tell me a joke")
        assert result["state"] == "no_plan"
        assert result["steps"] == []
        assert "note" in result

    def test_restricted_goal_is_not_auto_planned(self):
        # File listing needs a restricted tool; it is left to explicit steps
        # rather than auto-planned into a denied call.
        result = self._loop().run(user_id=1, goal="list the files in this directory")
        assert result["state"] == "no_plan"

    def test_explicit_steps_still_run(self):
        result = self._loop().run(
            user_id=1,
            goal="math",
            steps=[{"type": "tool", "tool": "calculator", "params": {"expression": "6*7"}}],
        )
        assert result["state"] == "completed"
        assert result["steps"][0]["result"]["result"] == 42


class TestEmptyStepsStillPlans:
    def test_empty_steps_list_triggers_auto_plan(self):
        # The web route sends steps=[]; that must not mean "explicit empty plan".
        from genesis_protocol.agentic.agent_loop import AgentLoop

        result = AgentLoop().run(user_id=1, goal="calculate 12+30", steps=[])
        assert result["state"] == "completed"
        assert result["steps"][0]["result"]["result"] == 42


class TestCodeExecutionIsSandboxed:
    """Code execution used a bare subprocess with the parent's env inherited.

    It must now run bounded: rlimits applied, secrets stripped from the child
    environment, and captured output capped.
    """

    def _run(self, code):
        import asyncio

        from genesis_protocol.ai.tool_system import get_tool_system

        return asyncio.run(get_tool_system().execute_tool("code_execution", {"code": code}))

    def test_simple_code_runs(self):
        result = self._run("print(sum(range(1,11)))")
        assert result.success is True
        assert "55" in result.data["output"]

    def test_limits_are_reported(self):
        result = self._run("print('ok')")
        limits = result.data["limits"]
        assert limits["memory_mb"] > 0
        assert limits["cpu_seconds"] > 0

    def test_child_does_not_inherit_secrets(self):
        result = self._run(
            "import os; print([k for k in os.environ if 'TOKEN' in k or 'KEY' in k or 'SECRET' in k])"
        )
        assert result.success is True
        assert result.data["output"].strip() == "[]"

    def test_infinite_loop_is_killed(self):
        result = self._run("while True: pass")
        assert result.success is False
        assert result.error

    def test_error_reports_traceback(self):
        result = self._run("raise ValueError('boom')")
        assert result.success is False
        assert "ValueError" in (result.error or "")


class TestChatReachesNotesAndTasks:
    """Notes and tasks were registered in the canonical registry but the chat
    tool system never exposed them, so a user could not save a note or add a
    task by asking. They are now registered, detected and parameterised.
    """

    def _agent(self):
        from genesis_protocol.ai.agent import GenesisAgent

        return GenesisAgent()

    def test_notes_save_is_detected_and_parameterised(self):
        agent = self._agent()
        query = "save note: buy milk tomorrow"
        assert "notes" in agent._detect_tool_needs(query)
        params = agent._build_tool_params("notes", query, user_id=7)
        assert params["action"] == "save"
        assert params["user_id"] == 7
        assert "buy milk" in params["content"]

    def test_notes_list_is_detected(self):
        agent = self._agent()
        query = "my notes"
        assert "notes" in agent._detect_tool_needs(query)
        assert agent._build_tool_params("notes", query, user_id=7)["action"] == "list"

    def test_task_create_is_detected_and_parameterised(self):
        agent = self._agent()
        query = "add task finish report"
        assert "task_manager" in agent._detect_tool_needs(query)
        params = agent._build_tool_params("task_manager", query, user_id=7)
        assert params["action"] == "create"
        assert params["name"] == "finish report"
        assert params["user_id"] == 7

    def test_task_list_is_detected(self):
        agent = self._agent()
        assert agent._build_tool_params("task_manager", "my tasks", user_id=7)["action"] == "list"

    def test_chat_can_save_and_list_a_note(self):
        import asyncio

        agent = self._agent()
        saved = asyncio.run(agent.tool_system.execute_tool(
            "notes", {"action": "save", "key": "k", "content": "v", "user_id": 7}
        ))
        assert saved.success is True
        listed = asyncio.run(agent.tool_system.execute_tool(
            "notes", {"action": "list", "user_id": 7}
        ))
        assert listed.success is True
        assert "k" in listed.data["notes"]

    def test_chat_can_create_and_list_a_task(self):
        import asyncio

        agent = self._agent()
        created = asyncio.run(agent.tool_system.execute_tool(
            "task_manager", {"action": "create", "name": "report", "user_id": 7}
        ))
        assert created.success is True
        listed = asyncio.run(agent.tool_system.execute_tool(
            "task_manager", {"action": "list", "user_id": 7}
        ))
        assert listed.success is True
        assert any(t["name"] == "report" for t in listed.data["tasks"])


class TestCapabilitiesResponseIsHonest:
    """The 'what can you do' reply printed a fixed list including docker and
    kubernetes whether or not those binaries existed.
    """

    def test_capabilities_exclude_missing_binaries(self):
        from genesis_protocol.ai.identity_router import get_identity_router

        text = get_identity_router()._what_capabilities()
        assert "NOT usable here" in text
        # kubectl is not installed in this environment; it must be listed as
        # unusable, not offered as a working capability.
        assert "kubectl" in text.split("NOT usable here")[1]

    def test_capabilities_mention_working_tools(self):
        from genesis_protocol.ai.identity_router import get_identity_router

        text = get_identity_router()._what_capabilities()
        assert "calculator" in text
        assert "bounded sandbox" in text


class TestChatHonoursToolPolicy:
    """The chat path ran every detected tool with no policy check, so a
    non-owner could reach restricted tools (code_execution, file_reader) the
    policy layer reserves for the owner. Chat now authorizes each tool by its
    registry permission.
    """

    def _agent(self, owner_ids):
        import os

        import genesis_protocol.agentic.policy as policy
        from genesis_protocol.ai.agent import GenesisAgent

        os.environ["GLUTEN_OWNER_IDS"] = ",".join(str(i) for i in owner_ids)
        # Drop the cached policy so it re-reads the owner ids set above.
        policy._default = None
        return GenesisAgent()

    def test_non_owner_cannot_reach_restricted_tools(self):
        agent = self._agent({1})
        policy = agent._tool_policy()
        for tool in ("code_execution", "file_reader"):
            decision = agent._authorize_chat_tool(policy, tool, 2)
            assert decision is not None and decision.allowed is False, tool

    def test_owner_can_reach_restricted_tools(self):
        agent = self._agent({1})
        policy = agent._tool_policy()
        decision = agent._authorize_chat_tool(policy, "code_execution", 1)
        assert decision is None or decision.allowed is True

    def test_safe_tools_allowed_for_everyone(self):
        agent = self._agent({1})
        policy = agent._tool_policy()
        for tool in ("web_search", "get_weather", "calculator", "notes", "task_manager"):
            decision = agent._authorize_chat_tool(policy, tool, 2)
            assert decision is None or decision.allowed is True, tool

    def test_denied_tool_is_reported_as_a_failure(self):
        import asyncio

        agent = self._agent({1})
        # A non-owner asking for code: the tool must not run and the failure
        # must be surfaced, not silently dropped.
        text, failures = asyncio.run(
            agent._execute_tools(["code_execution"], "run print(1)", user_id=2)
        )
        assert any("code_execution" in f for f in failures)
        assert text == "No tool results"


class TestArithmeticReachesTheToolPath:
    """Arithmetic only runs on the tool path, and the tool path only runs in
    autonomous mode. "calculate 17*23" triggered neither, so no calculator ran
    and the model answered from memory (the live probe returned 437).
    """

    def test_arithmetic_selects_autonomous_mode(self):
        from genesis_protocol.ai.autonomous_mode import get_mode_manager

        manager = get_mode_manager()
        assert manager.should_use_autonomous("calculate 17*23") is True
        assert manager.should_use_autonomous("what is 2+2") is True

    def test_ordinary_question_does_not(self):
        from genesis_protocol.ai.autonomous_mode import get_mode_manager

        manager = get_mode_manager()
        assert manager.should_use_autonomous("what is the capital of France") is False
        assert manager.should_use_autonomous("hi") is False

    def test_math_expression_helper(self):
        from genesis_protocol.ai.autonomous_mode import extract_math_expression

        assert extract_math_expression("calculate 17*23") == "17*23"
        assert extract_math_expression("what is the capital of France") == ""


class TestArithmeticDoesNotTriggerSearch:
    """Arithmetic needs no lookup, but "what is 2+2" matched the "what is"
    search keyword and returned a Brainly link beside the correct answer.
    """

    def test_arithmetic_suppresses_web_search(self):
        agent = _agent()
        needs = agent._detect_tool_needs("what is 2+2")
        assert "calculator" in needs
        assert "web_search" not in needs

    def test_non_arithmetic_question_still_searches(self):
        agent = _agent()
        assert "web_search" in agent._detect_tool_needs("what is the capital of France")
