"""Tests for v1.2 Integration"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPersonalityCommands:
    """Test personality commands."""
    
    def test_persona_command_gluttony(self):
        """Test /persona gluttony command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/persona gluttony")
        assert result.is_command is True
        assert result.handled is True
        assert "GLUTTONY" in result.response
        assert "fun" in result.response.lower()
    
    def test_persona_command_jarvis(self):
        """Test /persona jarvis command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/persona jarvis")
        assert result.is_command is True
        assert result.handled is True
        assert "JARVIS" in result.response
    
    def test_persona_command_friendly(self):
        """Test /persona friendly command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/persona friendly")
        assert result.is_command is True
        assert result.handled is True
        assert "FRIENDLY" in result.response
    
    def test_persona_command_developer(self):
        """Test /persona developer command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/persona developer")
        assert result.is_command is True
        assert result.handled is True
        assert "DEVELOPER" in result.response
    
    def test_persona_unknown(self):
        """Test unknown persona."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/persona unknown")
        assert result.is_command is True
        assert result.handled is True
        assert "Unknown persona" in result.response
    
    def test_mode_command(self):
        """Test /mode command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/mode casual")
        assert result.is_command is True
        assert result.handled is True
        assert "Casual" in result.response
    
    def test_reminder_command(self):
        """Test /remind command."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("/remind 30m Check email")
        assert result.is_command is True
        assert result.handled is True
        assert "30 m" in result.response
        assert "Check email" in result.response
    
    def test_regular_message_not_command(self):
        """Test that regular messages are not treated as commands."""
        from genesis_protocol.integration.commands import PersonalityCommands
        
        result = PersonalityCommands.parse_command("Hello, how are you?")
        assert result.is_command is False
        assert result.handled is False
        assert result.message == "Hello, how are you?"


class TestPersonalityEngine:
    """Test personality engine."""
    
    def test_persona_enum(self):
        """Test Persona enum values."""
        from genesis_protocol.personality import Persona
        
        assert Persona.NORMAL.value == "normal"
        assert Persona.GLUTTONY.value == "gluttony"
        assert Persona.JARVIS.value == "jarvis"
        assert Persona.FRIENDLY.value == "friendly"
        assert Persona.DEVELOPER.value == "developer"
    
    def test_conversation_mode_enum(self):
        """Test ConversationMode enum."""
        from genesis_protocol.personality import ConversationMode
        
        assert ConversationMode.ASSISTANT.value == "assistant"
        assert ConversationMode.FRIEND.value == "friend"
        assert ConversationMode.CASUAL.value == "casual"
    
    def test_get_personality_engine(self):
        """Test getting personality engine."""
        from genesis_protocol.personality import get_personality_engine
        
        engine = get_personality_engine(123)
        assert engine.user_id == 123
        assert engine.current_persona.value == "normal"
    
    def test_set_persona(self):
        """Test setting persona."""
        from genesis_protocol.personality import get_personality_engine, Persona
        
        engine = get_personality_engine(456)
        response = engine.set_persona(Persona.GLUTTONY)
        assert "Gluttony" in response
        assert engine.current_persona == Persona.GLUTTONY


class TestLongTermMemory:
    """Test long-term memory."""
    
    def test_memory_importance_enum(self):
        """Test MemoryImportance enum."""
        from genesis_protocol.memory import MemoryImportance
        
        assert MemoryImportance.CRITICAL.value == 5
        assert MemoryImportance.HIGH.value == 4
        assert MemoryImportance.MEDIUM.value == 3
        assert MemoryImportance.LOW.value == 2
    
    def test_add_memory(self):
        """Test adding memory."""
        from genesis_protocol.memory import LongTermMemory, MemoryImportance
        
        ltm = LongTermMemory(persist_path="./data/test_ltm")
        entry_id = ltm.add_memory(
            content="User prefers dark mode",
            user_id=123,
            importance=MemoryImportance.HIGH
        )
        assert entry_id is not None
        
        # Search for the memory
        results = ltm.search("dark mode", user_id=123)
        assert len(results) > 0
    
    def test_search_memory(self):
        """Test searching memory."""
        from genesis_protocol.memory import LongTermMemory, MemoryImportance
        
        ltm = LongTermMemory(persist_path="./data/test_ltm")
        
        ltm.add_memory("Python is awesome", user_id=999, importance=MemoryImportance.MEDIUM)
        ltm.add_memory("I love coding", user_id=999, importance=MemoryImportance.MEDIUM)
        
        results = ltm.search("Python", user_id=999)
        assert len(results) >= 1


class TestTaskQueue:
    """Test task queue."""
    
    def test_task_queue_add(self):
        """Test adding a task."""
        from genesis_protocol.tasks import TaskQueue, TaskStatus
        
        queue = TaskQueue(storage_path="./data/test_tasks")
        task_id = queue.add_task(
            name="Test Task",
            func_name="test_func",
            func_args={"key": "value"},
            user_id=123
        )
        assert task_id is not None
        
        task = queue.get_task(task_id)
        assert task is not None
        assert task.name == "Test Task"
        assert task.status == TaskStatus.PENDING
    
    def test_task_queue_stats(self):
        """Test task queue statistics."""
        from genesis_protocol.tasks import TaskQueue
        
        queue = TaskQueue(storage_path="./data/test_tasks")
        queue.add_task(name="Task 1", func_name="f1", user_id=1)
        queue.add_task(name="Task 2", func_name="f2", user_id=1)
        
        stats = queue.get_stats()
        assert stats['total'] >= 2
        assert stats['pending'] >= 2


class TestHumorEngine:
    """Test humor engine."""
    
    def test_get_random_joke(self):
        """Test getting a random joke."""
        from genesis_protocol.personality import HumorEngine
        
        joke = HumorEngine.get_random_joke()
        assert joke.setup is not None
        assert joke.punchline is not None
    
    def test_get_witty_response(self):
        """Test getting witty response."""
        from genesis_protocol.personality import HumorEngine
        
        response = HumorEngine.get_witty_response()
        assert response is not None
        assert len(response) > 0


class TestModuleStatus:
    """Test module status reporting."""
    
    def test_integration_get_module_status(self):
        """Test getting module status."""
        from genesis_protocol.integration import GenesisIntegration
        
        integration = GenesisIntegration()
        status = integration.get_module_status()
        
        assert 'personality' in status
        assert 'voice' in status
        assert 'vision' in status
        assert 'tasks' in status
        assert 'memory' in status
        
        # At least personality and memory should be ready
        assert status['personality'] is True
        assert status['memory'] is True
        assert status['tasks'] is True
