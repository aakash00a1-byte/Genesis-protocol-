"""Genesis Protocol - Unified Memory System

Short-term memory (Redis): Last 10 messages
Long-term memory (ChromaDB): Persistent vector storage
"""

import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("memory.unified")


@dataclass
class MemoryEntry:
    """Memory entry with metadata."""
    content: str
    timestamp: datetime
    type: str  # 'short_term', 'long_term', 'preference'
    importance: float = 0.5
    embedding: Optional[List[float]] = None


class ShortTermMemory:
    """Redis-based short-term memory (last 10 messages)."""
    
    KEY_PREFIX = "genesis:memory:short:"
    MAX_MESSAGES = 20
    
    def __init__(self):
        """Initialize short-term memory."""
        self._config = get_config()
        self._redis = None
        self._use_memory = False
        self._init_redis()
    
    def _init_redis(self):
        """Initialize Redis connection."""
        try:
            import redis
            self._redis = redis.Redis(
                host=self._config.memory.redis_host,
                port=self._config.memory.redis_port,
                password=self._config.memory.redis_password or None,
                db=self._config.memory.redis_db,
                decode_responses=True
            )
            self._redis.ping()
            self._use_memory = True
            logger.info("Short-term memory (Redis) initialized")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory fallback: {e}")
            self._redis = None
            self._memory_store: Dict[str, List[Dict]] = {}
    
    def add(self, chat_id: int, role: str, content: str, metadata: Dict = None) -> bool:
        """Add message to short-term memory."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        if self._redis:
            try:
                key = f"{self.KEY_PREFIX}{chat_id}"
                self._redis.lpush(key, json.dumps(entry))
                self._redis.ltrim(key, 0, self.MAX_MESSAGES - 1)
                return True
            except Exception as e:
                logger.error(f"Redis write error: {e}")
        
        # Fallback to in-memory
        if chat_id not in self._memory_store:
            self._memory_store[chat_id] = []
        self._memory_store[chat_id].append(entry)
        if len(self._memory_store[chat_id]) > self.MAX_MESSAGES:
            self._memory_store[chat_id] = self._memory_store[chat_id][-self.MAX_MESSAGES:]
        return True
    
    def get_recent(self, chat_id: int, limit: int = 10) -> List[Dict]:
        """Get recent messages from short-term memory."""
        if self._redis:
            try:
                key = f"{self.KEY_PREFIX}{chat_id}"
                items = self._redis.lrange(key, 0, limit - 1)
                return [json.loads(item) for item in items]
            except Exception as e:
                logger.error(f"Redis read error: {e}")
        
        return self._memory_store.get(chat_id, [])[-limit:]
    
    def clear(self, chat_id: int) -> bool:
        """Clear short-term memory for chat."""
        if self._redis:
            try:
                key = f"{self.KEY_PREFIX}{chat_id}"
                self._redis.delete(key)
                return True
            except Exception as e:
                logger.error(f"Redis clear error: {e}")
        
        if chat_id in self._memory_store:
            del self._memory_store[chat_id]
        return True


class LongTermMemory:
    """ChromaDB-based long-term memory (persistent vector storage)."""
    
    COLLECTION_NAME = "genesis_memory"
    
    def __init__(self):
        """Initialize long-term memory."""
        self._config = get_config()
        self._chroma = None
        self._collection = None
        self._use_vector = False
        self._init_chroma()
    
    def _init_chroma(self):
        """Initialize ChromaDB connection."""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Create client with persistence
            chroma_path = self._config.memory.chroma_db_path
            self._chroma = chromadb.Client(Settings(
                anonymized_telemetry=False,
                allow_reset=True
            ))
            
            # Try to get or create collection
            try:
                self._collection = self._chroma.get_collection(name=self.COLLECTION_NAME)
            except:
                self._collection = self._chroma.create_collection(
                    name=self.COLLECTION_NAME,
                    metadata={"description": "Genesis Protocol long-term memory"}
                )
            
            self._use_vector = True
            logger.info("Long-term memory (ChromaDB) initialized")
        except Exception as e:
            logger.warning(f"ChromaDB not available: {e}")
            self._chroma = None
            self._collection = None
    
    def store(self, chat_id: int, user_id: int, content: str, 
              memory_type: str = "general", importance: float = 0.5) -> bool:
        """Store memory with vector embedding."""
        if not self._use_vector:
            logger.debug("Vector storage not available")
            return False
        
        try:
            # Generate simple embedding (placeholder - use real embedding in production)
            embedding = self._simple_embedding(content)
            
            metadata = {
                "chat_id": str(chat_id),
                "user_id": str(user_id),
                "type": memory_type,
                "importance": importance,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            self._collection.add(
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata],
                ids=[f"{chat_id}_{datetime.utcnow().timestamp()}"]
            )
            return True
        except Exception as e:
            logger.error(f"Vector store error: {e}")
            return False
    
    def recall(self, query: str, chat_id: int = None, limit: int = 5) -> List[Dict]:
        """Recall relevant memories using vector similarity."""
        if not self._use_vector:
            return []
        
        try:
            query_embedding = self._simple_embedding(query)
            
            where_filter = {"chat_id": str(chat_id)} if chat_id else None
            
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter
            )
            
            memories = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    memories.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": results["distances"][0][i] if results.get("distances") else 1.0
                    })
            
            return memories
        except Exception as e:
            logger.error(f"Vector recall error: {e}")
            return []
    
    def store_preference(self, user_id: int, preference: str, value: Any) -> bool:
        """Store user preference."""
        return self.store(
            chat_id=0,
            user_id=user_id,
            content=f"Preference: {preference} = {value}",
            memory_type="preference",
            importance=0.8
        )
    
    def recall_preferences(self, user_id: int) -> List[Dict]:
        """Recall user preferences."""
        return self.recall("preference settings", chat_id=0)
    
    def _simple_embedding(self, text: str) -> List[float]:
        """Simple embedding fallback (use real embedding in production)."""
        # Simple hash-based embedding for demo
        import hashlib
        hash_val = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        embedding = []
        for i in range(1536):  # Standard dimension
            embedding.append(((hash_val >> i) & 1) * 0.5 + 0.25)
        return embedding


class UnifiedMemory:
    """
    Unified memory system combining short-term and long-term memory.
    
    - Short-term: Last 10 messages (Redis)
    - Long-term: Persistent memories (ChromaDB)
    """
    
    def __init__(self):
        """Initialize unified memory."""
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()
        self.logger = logging.getLogger("memory.unified")
    
    def store_interaction(self, chat_id: int, user_id: int, 
                         user_message: str, bot_response: str,
                         model_used: str, intent: str) -> bool:
        """Store complete interaction."""
        # Store in short-term
        self.short_term.add(chat_id, "user", user_message, {"model": model_used, "intent": intent})
        self.short_term.add(chat_id, "assistant", bot_response, {"model": model_used})
        
        # Store summary in long-term
        summary = f"User asked about {intent}: {user_message[:100]}... Bot responded using {model_used}"
        self.long_term.store(chat_id, user_id, summary, memory_type="interaction", importance=0.6)
        
        return True
    
    def get_context(self, chat_id: int, query: str = "", limit: int = 10) -> str:
        """
        Get combined context from both memory systems.
        
        Args:
            chat_id: Chat ID
            query: Query for relevance search (optional)
            limit: Max messages from short-term
            
        Returns:
            Combined context string
        """
        context_parts = []
        
        # Get recent short-term memories
        recent = self.short_term.get_recent(chat_id, limit)
        if recent:
            context_parts.append("Recent conversation:")
            for msg in recent:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                context_parts.append(f"- {role}: {content}")
        
        # Get relevant long-term memories if query provided
        if query:
            relevant = self.long_term.recall(query, chat_id, limit=3)
            if relevant:
                context_parts.append("\nRelevant past context:")
                for mem in relevant:
                    if mem.get("distance", 1.0) < 0.8:  # Only relevant ones
                        context_parts.append(f"- {mem['content'][:150]}...")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def store_summary(self, chat_id: int, user_id: int, summary: str) -> bool:
        """Store conversation summary."""
        return self.long_term.store(
            chat_id, user_id, f"Summary: {summary}",
            memory_type="summary",
            importance=0.7
        )
    
    def clear_all(self, chat_id: int) -> bool:
        """Clear all memories for a chat."""
        self.short_term.clear(chat_id)
        return True


# Singleton
_unified_memory: Optional[UnifiedMemory] = None


def get_unified_memory() -> UnifiedMemory:
    """Get or create unified memory singleton."""
    global _unified_memory
    if _unified_memory is None:
        _unified_memory = UnifiedMemory()
    return _unified_memory