"""Genesis Protocol - Vector Store

ChromaDB-based vector storage for semantic search.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from genesis_protocol.config import get_config, VectorDBType
from genesis_protocol.utils.logger import get_logger

logger = get_logger("memory.vector_store")


class VectorStore:
    """
    ChromaDB-based vector store for semantic memory.
    
    Provides embedding-based similarity search for context retrieval.
    """
    
    _instance: Optional["VectorStore"] = None
    _client = None
    _collection = None
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize vector store."""
        if self._client is not None:
            return
        
        config = get_config()
        
        # Only initialize if chroma is selected
        if config.memory.vector_db_type != VectorDBType.CHROMA:
            logger.warning(f"Vector store not initialized - type is {config.memory.vector_db_type}")
            return
        
        try:
            import chromadb
            from chromadb.config import Settings
            
            # Ensure directory exists
            db_path = Path(config.memory.chroma_db_path)
            db_path.mkdir(parents=True, exist_ok=True)
            
            # Initialize client
            self._client = chromadb.PersistentClient(
                path=str(db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                )
            )
            
            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name="genesis_memory",
                metadata={"description": "Genesis Protocol memory store"},
            )
            
            logger.info(
                "Vector store initialized",
                path=config.memory.chroma_db_path
            )
            
        except ImportError:
            logger.warning("ChromaDB not installed, vector store disabled")
            self._client = None
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            self._client = None
    
    async def add_memory(self, text: str, chat_id: int, 
                          message_id: str, metadata: Dict = None) -> str:
        """
        Add memory to vector store.
        
        Args:
            text: Text content
            chat_id: Telegram chat ID
            message_id: Message ID
            metadata: Additional metadata
            
        Returns:
            Memory ID
        """
        if not self._collection:
            return ""
        
        try:
            memory_id = f"{chat_id}:{message_id}"
            
            meta = {
                "chat_id": chat_id,
                "message_id": message_id,
                **(metadata or {})
            }
            
            self._collection.add(
                ids=[memory_id],
                documents=[text],
                metadatas=[meta],
            )
            
            logger.debug(f"Memory added: {memory_id}")
            
            return memory_id
            
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return ""
    
    async def similarity_search(self, query: str, filter: Dict = None,
                                 limit: int = 5) -> List[Dict[str, Any]]:
        """
        Search for similar memories.
        
        Args:
            query: Search query
            filter: Metadata filters
            limit: Maximum results
            
        Returns:
            List of relevant memories
        """
        if not self._collection:
            return []
        
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=limit,
                where=filter,
                include=["documents", "metadatas", "distances"],
            )
            
            memories = []
            for i, doc in enumerate(results.get("documents", [[]])[0] or []):
                memories.append({
                    "id": results["ids"][0][i],
                    "text": doc,
                    "distance": results["distances"][0][i] if "distances" in results else None,
                    "metadata": results["metadatas"][0][i] if "metadatas" in results else {},
                })
            
            logger.debug(f"Similarity search returned {len(memories)} results")
            
            return memories
            
        except Exception as e:
            logger.error(f"Similarity search failed: {e}")
            return []
    
    async def get_relevant_context(self, chat_id: int, query: str,
                                     max_memories: int = 5) -> str:
        """
        Get relevant context for AI processing.
        
        Args:
            chat_id: Telegram chat ID
            query: Query text
            max_memories: Maximum memories to retrieve
            
        Returns:
            Formatted context string
        """
        memories = await self.similarity_search(
            query=query,
            filter={"chat_id": chat_id},
            limit=max_memories,
        )
        
        if not memories:
            return ""
        
        context_parts = []
        for mem in memories:
            context_parts.append(f"[Relevant: {mem['text']}]")
        
        return "\n".join(context_parts)
    
    async def delete_memory(self, memory_id: str):
        """
        Delete memory by ID.
        
        Args:
            memory_id: Memory ID
        """
        if not self._collection:
            return
        
        try:
            self._collection.delete(ids=[memory_id])
            logger.debug(f"Memory deleted: {memory_id}")
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
    
    async def delete_chat_memories(self, chat_id: int):
        """
        Delete all memories for a chat.
        
        Args:
            chat_id: Telegram chat ID
        """
        if not self._collection:
            return
        
        try:
            self._collection.delete(where={"chat_id": chat_id})
            logger.info(f"All memories deleted for chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete chat memories: {e}")
    
    async def get_memory_count(self, chat_id: int = None) -> int:
        """
        Get count of stored memories.
        
        Args:
            chat_id: Optional chat ID filter
            
        Returns:
            Memory count
        """
        if not self._collection:
            return 0
        
        try:
            if chat_id:
                result = self._collection.get(where={"chat_id": chat_id})
            else:
                result = self._collection.get()
            
            return len(result.get("ids", []))
            
        except Exception as e:
            logger.error(f"Failed to get memory count: {e}")
            return 0
    
    async def reset(self):
        """Reset vector store (delete all memories)."""
        if not self._collection:
            return
        
        try:
            self._collection.delete(where={})
            logger.warning("Vector store reset")
        except Exception as e:
            logger.error(f"Failed to reset vector store: {e}")