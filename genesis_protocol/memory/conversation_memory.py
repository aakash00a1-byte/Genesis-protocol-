"""Genesis Protocol - Conversation Memory

Manages conversation history and context persistence.
"""

import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from genesis_protocol.models.conversation import Conversation, ConversationContext
from genesis_protocol.models.message import Message
from genesis_protocol.memory.redis_cache import RedisCache
from genesis_protocol.memory.vector_store import VectorStore
from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("memory.conversation")


class ConversationMemory:
    """
    Manages conversation history and context.
    
    Provides a 3-layer memory system:
    - Redis cache for fast access (recent messages)
    - Vector store for semantic search
    - SQLite for persistent storage
    """
    
    def __init__(self):
        """Initialize conversation memory."""
        config = get_config()
        self._cache = RedisCache()
        self._vector_store = VectorStore()
        self._max_history = config.memory.max_conversation_history
        
        logger.info("Conversation memory initialized")
    
    async def get_conversation(self, chat_id: int) -> Conversation:
        """
        Get or create conversation for chat.
        
        Args:
            chat_id: Telegram chat ID
            
        Returns:
            Conversation object
        """
        # Try cache first
        cache_key = f"conversation:{chat_id}"
        cached = await self._cache.get(cache_key)
        
        if cached:
            return self._deserialize_conversation(cached)
        
        # Create new conversation
        conversation = Conversation(
            id=cache_key,
            chat_id=chat_id,
            max_history=self._max_history,
        )
        
        await self._save_conversation(conversation)
        
        return conversation
    
    async def add_message(self, chat_id: int, message: Message):
        """
        Add message to conversation.
        
        Args:
            chat_id: Telegram chat ID
            message: Message to add
        """
        conversation = await self.get_conversation(chat_id)
        conversation.add_message(message)
        
        # Save to cache
        await self._save_conversation(conversation)
        
        # Add to vector store for semantic search
        if message.text:
            await self._vector_store.add_memory(
                text=message.text,
                chat_id=chat_id,
                message_id=message.id,
                metadata=message.to_dict(),
            )
        
        logger.debug(
            f"Message added to conversation",
            chat_id=chat_id,
            message_id=message.id
        )
    
    async def get_history(self, chat_id: int, limit: int = 100) -> List[Message]:
        """
        Get conversation history.
        
        Args:
            chat_id: Telegram chat ID
            limit: Maximum messages to return
            
        Returns:
            List of messages
        """
        conversation = await self.get_conversation(chat_id)
        return conversation.get_recent_messages(limit)
    
    async def search_memories(self, chat_id: int, query: str, 
                              limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search conversation memories semantically.
        
        Args:
            chat_id: Telegram chat ID
            query: Search query
            limit: Maximum results
            
        Returns:
            List of relevant memories
        """
        results = await self._vector_store.similarity_search(
            query=query,
            filter={"chat_id": chat_id},
            limit=limit,
        )
        
        return results
    
    async def get_context_for_ai(self, chat_id: int, 
                                  max_tokens: int = 8000) -> str:
        """
        Get formatted context for AI processing.
        
        Args:
            chat_id: Telegram chat ID
            max_tokens: Maximum tokens
            
        Returns:
            Formatted context string
        """
        conversation = await self.get_conversation(chat_id)
        
        # Get relevant memories
        recent = conversation.get_recent_messages(10)
        
        if not recent:
            return ""
        
        # Format context
        context_parts = []
        
        for msg in recent:
            role = "User" if msg.direction.value == "incoming" else "Assistant"
            content = msg.text or ""
            
            if msg.message_type.value == "voice" and not content:
                content = "[Voice message]"
            elif msg.message_type.value == "image" and not content:
                content = "[Image]"
            
            context_parts.append(f"{role}: {content}")
        
        context = "\n".join(context_parts[-20:])
        
        # Check token limit
        if len(context.split()) > max_tokens:
            context = " ".join(context.split()[-max_tokens:])
        
        return context
    
    async def clear_conversation(self, chat_id: int):
        """
        Clear conversation history.
        
        Args:
            chat_id: Telegram chat ID
        """
        cache_key = f"conversation:{chat_id}"
        await self._cache.delete(cache_key)
        
        logger.info(f"Conversation cleared", chat_id=chat_id)
    
    async def _save_conversation(self, conversation: Conversation):
        """Save conversation to cache."""
        cache_key = f"conversation:{conversation.chat_id}"
        data = self._serialize_conversation(conversation)
        
        ttl = get_config().memory.redis_session_ttl
        await self._cache.set(cache_key, data, ttl=ttl)
    
    def _serialize_conversation(self, conversation: Conversation) -> str:
        """Serialize conversation to JSON."""
        return json.dumps(conversation.to_dict())
    
    def _deserialize_conversation(self, data: str) -> Conversation:
        """Deserialize conversation from JSON."""
        obj = json.loads(data)
        
        messages = []
        for msg_data in obj.get("messages", []):
            msg = Message(
                id=msg_data["id"],
                chat_id=msg_data["chat_id"],
                user_id=msg_data["user_id"],
            )
            messages.append(msg)
        
        context_data = obj.get("context", {})
        context = ConversationContext(
            summary=context_data.get("summary", ""),
            key_topics=context_data.get("key_topics", []),
        )
        
        conversation = Conversation(
            id=obj["id"],
            chat_id=obj["chat_id"],
            messages=messages,
            context=context,
            max_history=obj.get("max_history", self._max_history),
        )
        
        return conversation
    
    async def prune_old_conversations(self, max_age_hours: int = 168):
        """
        Prune conversations older than max age.
        
        Args:
            max_age_hours: Maximum age in hours (default: 1 week)
        """
        logger.info(f"Pruning conversations older than {max_age_hours} hours")
        # In production, implement cleanup of old conversations from vector store
        pass