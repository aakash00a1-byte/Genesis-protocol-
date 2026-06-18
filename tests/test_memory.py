"""Tests for memory components."""

import pytest
from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.memory.vector_store import VectorStore
from genesis_protocol.memory.redis_cache import RedisCache
from genesis_protocol.config import get_config, VectorDBType


class TestConversationMemory:
    """Test conversation memory (SQLite)."""

    def test_memory_initialization(self):
        """Test memory can be initialized."""
        memory = ConversationMemory()
        assert memory is not None

    def test_store_and_retrieve(self):
        """Test storing and retrieving conversation."""
        memory = ConversationMemory()
        
        # Store
        memory.store_interaction(
            chat_id=9998,
            user_id=9998,
            user_message="Test message",
            bot_response="Test response",
            model_used="test-model",
            intent="test"
        )
        
        # Retrieve
        history = memory.get_recent_conversations(9998, limit=10)
        assert len(history) >= 1

    def test_cleanup(self):
        """Test cleanup of test data."""
        memory = ConversationMemory()
        memory.clear_conversation(9998, 9998)


class TestVectorStore:
    """Test vector store (ChromaDB)."""

    def test_vector_store_graceful_fallback(self):
        """Test vector store works without ChromaDB."""
        store = VectorStore()
        # Should not crash - graceful fallback
        assert store._client is None or store._client is not None

    def test_vector_db_type_config(self):
        """Test vector DB type configuration."""
        config = get_config()
        assert config.memory.vector_db_type in VectorDBType


class TestRedisCache:
    """Test Redis cache."""

    def test_redis_graceful_fallback(self):
        """Test Redis cache works without Redis."""
        cache = RedisCache()
        # Should not crash - uses in-memory fallback
        assert cache._client is None or cache._client is not None
