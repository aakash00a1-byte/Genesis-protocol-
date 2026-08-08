"""Genesis Protocol - Test Configuration"""

import pytest
import sys
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_config():
    """Mock configuration for tests."""
    from genesis_protocol.config import Config
    
    config = Config()
    config.groq.api_key = "test_key"
    config.openai.api_key = "test_key"
    
    return config


@pytest.fixture
def mock_message():
    """Mock message for tests."""
    from genesis_protocol.models.message import Message, MessageType, MessageDirection
    
    return Message(
        id="test_123",
        chat_id=123456,
        user_id=789,
        message_type=MessageType.TEXT,
        direction=MessageDirection.INCOMING,
        text="Test message",
    )


@pytest.fixture
def mock_user():
    """Mock user for tests."""
    from genesis_protocol.models.user import User
    
    return User(
        id=789,
        username="testuser",
        first_name="Test",
        last_name="User",
    )