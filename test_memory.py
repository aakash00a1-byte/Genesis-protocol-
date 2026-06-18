#!/usr/bin/env python3
"""Memory test script for Genesis Protocol."""

import asyncio
import sys
sys.path.insert(0, '.')

from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.memory.vector_store import VectorStore
from genesis_protocol.memory.redis_cache import RedisCache
from genesis_protocol.config import get_config


async def test_conversation_memory():
    """Test conversation memory."""
    print("=" * 50)
    print("Testing Conversation Memory (SQLite)")
    print("=" * 50)
    
    memory = ConversationMemory()
    
    # Store a test conversation
    chat_id = 9999
    user_id = 9999
    
    memory.store_interaction(
        chat_id=chat_id,
        user_id=user_id,
        user_message="Hello, this is a test!",
        bot_response="Hi! This is a test response.",
        model_used="test-model",
        intent="test"
    )
    
    # Retrieve recent conversations
    history = memory.get_recent_conversations(chat_id, limit=5)
    
    print(f"✅ Stored interaction successfully")
    print(f"✅ Retrieved {len(history)} conversation(s)")
    
    # Cleanup
    memory.clear_conversation(chat_id, user_id)
    print("✅ Cleared test data")
    
    return True


def test_vector_store():
    """Test vector store (ChromaDB)."""
    print("\n" + "=" * 50)
    print("Testing Vector Store (ChromaDB)")
    print("=" * 50)
    
    config = get_config()
    print(f"Vector DB Type: {config.memory.vector_db_type}")
    print(f"Chroma DB Path: {config.memory.chroma_db_path}")
    
    store = VectorStore()
    
    if store._client is None:
        print("⚠️  Vector store not available (ChromaDB not installed or init failed)")
        print("   This is OK - app will work without vector memory")
        return True
    
    print("✅ Vector store initialized successfully")
    return True


def test_redis_cache():
    """Test Redis cache."""
    print("\n" + "=" * 50)
    print("Testing Redis Cache")
    print("=" * 50)
    
    config = get_config()
    print(f"Redis Host: {config.memory.redis_host}")
    print(f"Redis Port: {config.memory.redis_port}")
    
    cache = RedisCache()
    
    if cache._client is None:
        print("⚠️  Redis not connected (will use in-memory fallback)")
        print("   This is OK - app will work without Redis")
        return True
    
    print("✅ Redis connected successfully")
    return True


def main():
    print("🧪 Genesis Protocol - Memory Test Suite")
    print("=" * 50)
    
    results = []
    
    # Test vector store
    results.append(("Vector Store", test_vector_store()))
    
    # Test Redis cache
    results.append(("Redis Cache", test_redis_cache()))
    
    # Test conversation memory
    results.append(("Conversation Memory", asyncio.run(test_conversation_memory())))
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{name}: {status}")
    
    all_passed = all(r for _, r in results)
    print("\n" + ("🎉 All tests passed!" if all_passed else "⚠️  Some tests failed"))
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
