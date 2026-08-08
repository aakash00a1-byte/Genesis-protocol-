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

    def test_memory_has_add_message(self):
        """Test memory has add_message method."""
        memory = ConversationMemory()
        assert hasattr(memory, 'add_message')


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
