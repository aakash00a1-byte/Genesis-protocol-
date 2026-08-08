"""Tests for v1.4 Interaction Layer"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['DATA_PATH'] = tempfile.mkdtemp()


class TestContextManager:
    def test_get_context(self):
        from genesis_protocol.interaction.context_manager import ContextManager
        manager = ContextManager()
        ctx = manager.get_context(1)
        assert ctx.user_id == 1
        assert ctx.persona is not None

    def test_context_to_prompt(self):
        from genesis_protocol.interaction.context_manager import UnifiedContext
        ctx = UnifiedContext(user_id=1)
        ctx.user_name = "Test"
        ctx.persona = "gluttony"
        prompt = ctx.to_prompt_context()
        assert "Test" in prompt
        assert "gluttony" in prompt


class TestToolSystem:
    def test_calculator(self):
        from genesis_protocol.interaction.tool_system import CalculatorTool
        calc = CalculatorTool()
        result = calc.execute(expression="2+2")
        assert result['success'] is True
        assert result['result'] == 4

    def test_calculator_power(self):
        from genesis_protocol.interaction.tool_system import CalculatorTool
        calc = CalculatorTool()
        result = calc.execute(expression="2^8")
        assert result['success'] is True
        assert result['result'] == 256

    def test_notes_tool(self):
        from genesis_protocol.interaction.tool_system import NotesTool
        notes = NotesTool()
        save_result = notes.execute(action="save", key="test", content="Hello world")
        assert save_result['success'] is True
        get_result = notes.execute(action="get", key="test")
        assert get_result['success'] is True
        assert get_result['note']['content'] == "Hello world"

    def test_notes_list(self):
        from genesis_protocol.interaction.tool_system import NotesTool
        notes = NotesTool()
        notes.execute(action="save", key="note1", content="Content 1")
        notes.execute(action="save", key="note2", content="Content 2")
        result = notes.execute(action="list")
        assert result['success'] is True
        assert "note1" in result['notes']
        assert "note2" in result['notes']

    def test_tool_registry(self):
        from genesis_protocol.interaction.tool_system import ToolRegistry
        registry = ToolRegistry()
        tools = registry.get_all_tools()
        assert len(tools) >= 7
        assert any(t.name == "calculator" for t in tools)
        assert any(t.name == "notes" for t in tools)

    def test_execute_tool(self):
        from genesis_protocol.interaction.tool_system import ToolRegistry
        registry = ToolRegistry()
        result = registry.execute_tool("calculator", {"expression": "10*5"})
        assert result['success'] is True
        assert result['result'] == 50


class TestSessionManager:
    def test_create_session(self):
        from genesis_protocol.interaction.session_manager import SessionManager
        manager = SessionManager(storage_path=tempfile.mkdtemp())
        session = manager.create_session(1)
        assert session.user_id == 1
        assert session.session_id is not None

    def test_session_info(self):
        from genesis_protocol.interaction.session_manager import SessionManager
        manager = SessionManager(storage_path=tempfile.mkdtemp())
        manager.create_session(1)
        info = manager.get_session_info()
        assert info['active'] is True
        assert info['user_id'] == 1


class TestAgentActions:
    def test_action_history(self):
        from genesis_protocol.interaction.agent_actions import AgentActionHandler
        handler = AgentActionHandler()
        handler.execute_action("create_task", {"name": "test"}, user_id=1)
        history = handler.get_action_history()
        assert len(history) == 1

    def test_action_types(self):
        from genesis_protocol.interaction.agent_actions import AgentActionType
        assert AgentActionType.CREATE_TASK.value == "create_task"
        assert AgentActionType.SAVE_MEMORY.value == "save_memory"
        assert AgentActionType.SEARCH_MEMORY.value == "search_memory"


class TestVoicePipeline:
    def test_voice_pipeline_status(self):
        from genesis_protocol.interaction.voice_pipeline import VoicePipeline
        pipeline = VoicePipeline()
        status = pipeline.get_status()
        assert 'stt_configured' in status
        assert 'tts_configured' in status
        assert status['stt_configured'] is False

    def test_interrupt(self):
        from genesis_protocol.interaction.voice_pipeline import VoicePipeline
        pipeline = VoicePipeline()
        pipeline.interrupt()
        assert pipeline._interrupt_flag is True


class TestVisionPipeline:
    def test_validate_image(self):
        from genesis_protocol.interaction.vision_pipeline import VisionPipeline
        pipeline = VisionPipeline()
        assert pipeline.validate_image(b'\xff\xd8\xff\xe0test') is True
        assert pipeline.validate_image(b'\x89PNG\r\n\x1a\ntest') is True
        assert pipeline.validate_image(b'invalid') is False

    def test_vision_status(self):
        from genesis_protocol.interaction.vision_pipeline import VisionPipeline
        pipeline = VisionPipeline()
        status = pipeline.get_status()
        assert 'provider_configured' in status
        assert status['images_analyzed'] == 0
