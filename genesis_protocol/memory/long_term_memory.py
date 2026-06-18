"""Long-term Memory with ChromaDB - Genesis Protocol v1.1"""

import json
import time
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


class MemoryImportance(Enum):
    """Memory importance levels."""
    CRITICAL = 5   # Never forget, user explicitly marked important
    HIGH = 4      # Important facts about user
    MEDIUM = 3     # Regular conversation context
    LOW = 2       # Trivia, casual mentions
    FORGETTABLE = 1  # Can be pruned


@dataclass
class MemoryEntry:
    """A memory entry with importance scoring."""
    id: str
    content: str
    importance: MemoryImportance = MemoryImportance.MEDIUM
    category: str = "conversation"
    user_id: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # For ChromaDB vector storage
    vector_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'content': self.content,
            'importance': self.importance.value,
            'category': self.category,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'access_count': self.access_count,
            'last_accessed': self.last_accessed.isoformat(),
            'metadata': self.metadata
        }


class LongTermMemory:
    """Long-term memory system with ChromaDB integration."""
    
    def __init__(self, persist_path: str = "./data/chroma_db"):
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self._memory_index: Dict[str, MemoryEntry] = {}
        self._chroma_client = None
        self._collection = None
        self._init_chroma()
        self._load_index()
    
    def _init_chroma(self):
        """Initialize ChromaDB."""
        try:
            import chromadb
            from chromadb.config import Settings
            
            self._chroma_client = chromadb.PersistentClient(
                path=str(self.persist_path),
                settings=Settings(anonymized_telemetry=False)
            )
            self._collection = self._chroma_client.get_or_create_collection(
                name="genesis_memory",
                metadata={"description": "Long-term memory for Genesis Protocol"}
            )
        except ImportError:
            print("ChromaDB not available, using in-memory storage")
    
    def _load_index(self):
        """Load memory index from disk."""
        index_path = self.persist_path / "memory_index.json"
        if index_path.exists():
            with open(index_path, 'r') as f:
                data = json.load(f)
            for entry_data in data:
                entry_data['importance'] = MemoryImportance(entry_data['importance'])
                entry_data['created_at'] = datetime.fromisoformat(entry_data['created_at'])
                entry_data['last_accessed'] = datetime.fromisoformat(entry_data['last_accessed'])
                entry = MemoryEntry(**entry_data)
                self._memory_index[entry.id] = entry
    
    def _save_index(self):
        """Save memory index to disk."""
        index_path = self.persist_path / "memory_index.json"
        data = [entry.to_dict() for entry in self._memory_index.values()]
        with open(index_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_memory(
        self,
        content: str,
        user_id: int,
        importance: MemoryImportance = MemoryImportance.MEDIUM,
        category: str = "conversation",
        metadata: Dict[str, Any] = None
    ) -> str:
        """Add a memory entry."""
        import uuid
        
        entry_id = str(uuid.uuid4())[:8]
        entry = MemoryEntry(
            id=entry_id,
            content=content,
            importance=importance,
            category=category,
            user_id=user_id,
            metadata=metadata or {}
        )
        
        self._memory_index[entry_id] = entry
        
        # Add to ChromaDB
        if self._collection:
            self._collection.add(
                documents=[content],
                metadatas=[{
                    'entry_id': entry_id,
                    'user_id': user_id,
                    'importance': importance.value
                }],
                ids=[entry_id]
            )
        
        self._save_index()
        return entry_id
    
    def search(
        self,
        query: str,
        user_id: Optional[int] = None,
        limit: int = 5,
        min_importance: MemoryImportance = MemoryImportance.LOW
    ) -> List[MemoryEntry]:
        """Search memories by semantic similarity."""
        results = []
        
        if self._collection:
            try:
                query_results = self._collection.query(
                    query_texts=[query],
                    n_results=limit * 2  # Over-fetch to filter
                )
                
                for i, doc_id in enumerate(query_results['ids'][0]):
                    entry = self._memory_index.get(doc_id)
                    if entry:
                        # Filter by user and importance
                        if user_id and entry.user_id != user_id:
                            continue
                        if entry.importance.value < min_importance.value:
                            continue
                        results.append(entry)
            except Exception:
                pass
        
        # Fallback: simple text search
        if not results:
            query_lower = query.lower()
            for entry in self._memory_index.values():
                if (not user_id or entry.user_id == user_id) and \
                   entry.importance.value >= min_importance.value:
                    if query_lower in entry.content.lower():
                        results.append(entry)
        
        # Sort by importance and recency
        results.sort(
            key=lambda e: (e.importance.value, e.last_accessed.timestamp()),
            reverse=True
        )
        
        return results[:limit]
    
    def get_recent(
        self,
        user_id: int,
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[MemoryEntry]:
        """Get recent memories for a user."""
        memories = [
            e for e in self._memory_index.values()
            if e.user_id == user_id
            and (not category or e.category == category)
        ]
        
        memories.sort(key=lambda e: e.last_accessed.timestamp(), reverse=True)
        return memories[:limit]
    
    def update_importance(self, entry_id: str, importance: MemoryImportance):
        """Update memory importance."""
        entry = self._memory_index.get(entry_id)
        if entry:
            entry.importance = importance
            self._save_index()
    
    def access_memory(self, entry_id: str):
        """Record memory access."""
        entry = self._memory_index.get(entry_id)
        if entry:
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self._save_index()
    
    def prune_memories(self, keep_importance: MemoryImportance = MemoryImportance.MEDIUM):
        """Remove low-importance memories to save space."""
        to_remove = [
            entry_id for entry_id, entry in self._memory_index.items()
            if entry.importance.value < keep_importance.value
            and entry.access_count == 0
        ]
        
        for entry_id in to_remove:
            del self._memory_index[entry_id]
            if self._collection:
                try:
                    self._collection.delete(ids=[entry_id])
                except Exception:
                    pass
        
        if to_remove:
            self._save_index()
        
        return len(to_remove)
    
    def get_user_memories_count(self, user_id: int) -> int:
        """Get total memories for a user."""
        return sum(1 for e in self._memory_index.values() if e.user_id == user_id)
    
    def clear_user_memories(
        self, 
        user_id: int, 
        keep_importance: MemoryImportance = MemoryImportance.CRITICAL
    ):
        """Clear memories for a user, keeping important ones."""
        to_remove = [
            entry_id for entry_id, entry in self._memory_index.items()
            if entry.user_id == user_id
            and entry.importance.value < keep_importance.value
        ]
        
        for entry_id in to_remove:
            del self._memory_index[entry_id]
        
        self._save_index()
        return len(to_remove)


# Global instance
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """Get global long-term memory instance."""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory
