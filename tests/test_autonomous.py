"""Tests for v1.3 Autonomous Layer"""

import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set temp data path for tests
os.environ['DATA_PATH'] = tempfile.mkdtemp()


class TestEventSystem:
    """Test event system."""

    def test_log_event(self):
        """Test logging an event."""
        from genesis_protocol.autonomous.event_system import EventLogger, EventType
        
        logger = EventLogger(persist_path=tempfile.mkdtemp())
        event = logger.log(EventType.STARTUP, "Test event")
        
        assert event.message == "Test event"
        assert event.type == EventType.STARTUP

    def test_get_recent_events(self):
        """Test getting recent events."""
        from genesis_protocol.autonomous.event_system import EventLogger, EventType
        
        logger = EventLogger(persist_path=tempfile.mkdtemp())
        logger.log(EventType.STARTUP, "Event 1")
        logger.log(EventType.MOOD_CHANGE, "Event 2")
        
        events = logger.get_recent(limit=10)
        assert len(events) == 2

    def test_event_stats(self):
        """Test event statistics."""
        from genesis_protocol.autonomous.event_system import EventLogger, EventType
        
        logger = EventLogger(persist_path=tempfile.mkdtemp())
        logger.log(EventType.STARTUP, "Test")
        logger.log(EventType.EXCEPTION, "Error", severity="error")
        
        stats = logger.get_stats()
        assert stats['total'] == 2
        assert stats['by_severity']['error'] == 1


class TestMoodEngine:
    """Test mood engine."""

    def test_set_mood(self):
        """Test setting mood."""
        from genesis_protocol.autonomous.mood_engine import MoodEngine, Mood
        
        engine = MoodEngine(user_id=1)
        response = engine.set_mood(Mood.PLAYFUL)
        
        assert engine.current_mood == Mood.PLAYFUL
        assert "Playful" in response

    def test_mood_info(self):
        """Test getting mood info."""
        from genesis_protocol.autonomous.mood_engine import MoodEngine, Mood
        
        engine = MoodEngine(user_id=1)
        engine.set_mood(Mood.FOCUSED)
        
        info = engine.get_mood_info()
        assert info['current'] == 'focused'
        assert info['emoji'] == '🎯'

    def test_adjust_mood_context(self):
        """Test mood adjustment based on context."""
        from genesis_protocol.autonomous.mood_engine import MoodEngine, Mood
        
        engine = MoodEngine(user_id=1)
        engine.set_mood(Mood.CALM)
        
        # Simulate excited message
        engine.adjust_mood_based_on_context("I'm so excited about this!")
        
        assert engine.current_mood == Mood.PLAYFUL


class TestReflectionEngine:
    """Test reflection engine."""

    def test_record_conversation(self):
        """Test recording conversation."""
        from genesis_protocol.autonomous.reflection_engine import ReflectionEngine
        
        engine = ReflectionEngine()
        engine.record_conversation(1, "Hello", "Hi there!")
        
        assert engine.conversation_count == 1

    def test_generate_reflection(self):
        """Test generating reflection."""
        from genesis_protocol.autonomous.reflection_engine import ReflectionEngine
        
        engine = ReflectionEngine()
        engine.conversation_count = 5
        reflection = engine.generate_reflection()
        
        assert 'timestamp' in reflection
        assert reflection['conversation_count'] == 5

    def test_answer_self_question_name(self):
        """Test answering name question."""
        from genesis_protocol.autonomous.reflection_engine import ReflectionEngine
        
        engine = ReflectionEngine()
        answer = engine.answer_self_question("What's my name?", user_id=1)
        
        assert "name" in answer.lower()


class TestUserProfile:
    """Test user profile."""

    def test_create_profile(self):
        """Test creating user profile."""
        from genesis_protocol.autonomous.user_profile import UserProfile
        
        profile = UserProfile(user_id=1)
        assert profile.user_id == 1
        assert profile.interaction_count == 0

    def test_learn_from_message(self):
        """Test learning from message."""
        from genesis_protocol.autonomous.user_profile import UserProfile
        
        profile = UserProfile(user_id=1)
        profile.update_from_message("I have a bug in my Python code")
        
        assert profile.favorite_topics == ['coding']
        assert profile.conversation_style == "technical"

    def test_detect_hindi(self):
        """Test Hindi language detection."""
        from genesis_protocol.autonomous.user_profile import UserProfile
        
        profile = UserProfile(user_id=1)
        profile.update_from_message("Kya haal hai?")
        
        assert profile.preferred_language == "hi"

    def test_detect_casual_style(self):
        """Test casual style detection."""
        from genesis_protocol.autonomous.user_profile import UserProfile
        
        profile = UserProfile(user_id=1)
        profile.update_from_message("Hey bro, what's up? haha lol")
        
        assert profile.conversation_style == "casual"


class TestAutonomousDaemon:
    """Test autonomous daemon."""

    def test_daemon_status(self):
        """Test getting daemon status."""
        from genesis_protocol.autonomous.autonomous_daemon import AutonomousDaemon
        
        daemon = AutonomousDaemon()
        status = daemon.get_status()
        
        assert 'running' in status
        assert status['running'] is False

    def test_increment_conversation(self):
        """Test conversation counter."""
        from genesis_protocol.autonomous.autonomous_daemon import AutonomousDaemon
        
        daemon = AutonomousDaemon()
        daemon.increment_conversation()
        
        assert daemon._conversation_count == 1


class TestServiceManager:
    """Test service manager."""

    def test_get_status(self):
        """Test getting service status."""
        from genesis_protocol.autonomous.service_manager import AutonomousServiceManager
        
        manager = AutonomousServiceManager()
        status = manager.get_status()
        
        assert 'running' in status
        assert 'services' in status

    def test_get_full_state(self):
        """Test getting full state."""
        from genesis_protocol.autonomous.service_manager import AutonomousServiceManager
        
        manager = AutonomousServiceManager()
        state = manager.get_full_state()
        
        assert 'persona' in state
        assert 'mood' in state
        assert 'tasks_pending' in state
        assert 'memories' in state
        assert 'health' in state


class TestMoodValues:
    """Test mood enum values."""

    def test_all_moods(self):
        """Test all mood values exist."""
        from genesis_protocol.autonomous.mood_engine import Mood
        
        assert Mood.CALM.value == "calm"
        assert Mood.PLAYFUL.value == "playful"
        assert Mood.FOCUSED.value == "focused"
        assert Mood.DEVELOPER.value == "developer"
        assert Mood.SLEEPY.value == "sleepy"
