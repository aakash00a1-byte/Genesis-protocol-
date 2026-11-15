"""
⚡ Genesis Memory Agent ⚡
Persistent memory system for Genesis Protocol
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class MemoryEntry:
    id: str
    content: str
    category: str  # lesson, failure, success, knowledge, interaction
    tags: List[str]
    importance: float  # 0-1
    created_at: str
    updated_at: str
    access_count: int = 0
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MemoryAgent:
    """Autonomous memory system for Genesis Protocol."""
    
    VERSION = "1.0.0"
    
    CATEGORIES = [
        "lesson",      # Learned lessons
        "failure",      # Failed attempts
        "success",     # Successful operations
        "knowledge",   # General knowledge
        "interaction", # User interactions
        "code",        # Code patterns
        "system",      # System state
    ]
    
    def __init__(self, storage_path: str = "./data/memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._memory: Dict[str, MemoryEntry] = {}
        self._index: Dict[str, List[str]] = {}  # tag -> memory_ids
        self._load_memory()
    
    def _generate_id(self, content: str) -> str:
        """Generate unique ID from content hash."""
        return hashlib.md5(f"{content}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    
    def _load_memory(self):
        """Load memory from disk."""
        memory_file = self.storage_path / "memory.json"
        if memory_file.exists():
            try:
                with open(memory_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    entry = MemoryEntry(**item)
                    self._memory[entry.id] = entry
                    # Rebuild index
                    for tag in entry.tags:
                        if tag not in self._index:
                            self._index[tag] = []
                        self._index[tag].append(entry.id)
            except Exception as e:
                print(f"Memory load error: {e}")
    
    def _save_memory(self):
        """Save memory to disk."""
        memory_file = self.storage_path / "memory.json"
        try:
            data = [asdict(m) for m in self._memory.values()]
            with open(memory_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Memory save error: {e}")
    
    def remember(
        self,
        content: str,
        category: str = "knowledge",
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
        metadata: Optional[Dict] = None
    ) -> MemoryEntry:
        """Store a memory."""
        if category not in self.CATEGORIES:
            category = "knowledge"
        
        tags = tags or []
        entry = MemoryEntry(
            id=self._generate_id(content),
            content=content,
            category=category,
            tags=tags,
            importance=importance,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        
        self._memory[entry.id] = entry
        
        # Update index
        for tag in entry.tags:
            if tag not in self._index:
                self._index[tag] = []
            if entry.id not in self._index[tag]:
                self._index[tag].append(entry.id)
        
        self._save_memory()
        return entry
    
    def recall(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[MemoryEntry]:
        """Recall memories based on criteria."""
        results = []
        
        # Filter by category
        if category:
            results = [m for m in self._memory.values() if m.category == category]
        else:
            results = list(self._memory.values())
        
        # Filter by tags
        if tags:
            tag_ids = set()
            for tag in tags:
                if tag in self._index:
                    tag_ids.update(self._index[tag])
            results = [m for m in results if m.id in tag_ids]
        
        # Sort by importance and recency
        results.sort(key=lambda m: (m.importance, m.access_count, m.created_at), reverse=True)
        
        # Update access counts
        for entry in results[:limit]:
            entry.access_count += 1
            entry.updated_at = datetime.now().isoformat()
        
        return results[:limit]
    
    def learn_from_interaction(
        self,
        user_message: str,
        bot_response: str,
        success: bool = True,
        tags: Optional[List[str]] = None
    ):
        """Learn from user interaction."""
        category = "success" if success else "failure"
        
        memory_content = f"User: {user_message}\nBot: {bot_response}"
        
        self.remember(
            content=memory_content,
            category="interaction",
            tags=tags or ["interaction"],
            importance=0.7 if success else 0.9,
            metadata={"success": success}
        )
    
    def learn_code_pattern(
        self,
        pattern_name: str,
        code: str,
        description: str,
        tags: Optional[List[str]] = None
    ):
        """Learn a code pattern."""
        content = f"# {pattern_name}\n\n{description}\n\n```\n{code}\n```"
        
        self.remember(
            content=content,
            category="code",
            tags=tags or ["code", pattern_name],
            importance=0.6
        )
    
    def remember_lesson(
        self,
        lesson: str,
        context: str,
        outcome: str,
        tags: Optional[List[str]] = None
    ):
        """Remember a learned lesson."""
        content = f"Context: {context}\n\nLesson: {lesson}\n\nOutcome: {outcome}"
        
        self.remember(
            content=content,
            category="lesson",
            tags=tags or ["lesson"],
            importance=0.8
        )
    
    def get_wisdom(self, limit: int = 20) -> List[str]:
        """Get accumulated wisdom (high-importance memories)."""
        wisdom = self.recall(limit=limit)
        return [m.content for m in wisdom if m.importance >= 0.7]
    
    def get_stats(self) -> Dict:
        """Get memory statistics."""
        by_category = {}
        for entry in self._memory.values():
            by_category[entry.category] = by_category.get(entry.category, 0) + 1
        
        return {
            "total_memories": len(self._memory),
            "by_category": by_category,
            "tags_count": len(self._index),
            "high_importance": len([m for m in self._memory.values() if m.importance >= 0.8])
        }
    
    def forget(self, memory_id: str) -> bool:
        """Forget a memory."""
        if memory_id in self._memory:
            entry = self._memory.pop(memory_id)
            
            # Remove from index
            for tag in entry.tags:
                if tag in self._index and memory_id in self._index[tag]:
                    self._index[tag].remove(memory_id)
            
            self._save_memory()
            return True
        return False
    
    def consolidate(self, keep_count: int = 1000):
        """Keep only most important memories."""
        if len(self._memory) <= keep_count:
            return
        
        # Sort by importance
        sorted_memories = sorted(
            self._memory.values(),
            key=lambda m: (m.importance, m.access_count),
            reverse=True
        )
        
        # Keep only top memories
        keep_ids = {m.id for m in sorted_memories[:keep_count]}
        
        # Remove others
        to_remove = [mid for mid in self._memory if mid not in keep_ids]
        for mid in to_remove:
            self.forget(mid)


# Global singleton
_memory_agent: Optional[MemoryAgent] = None


def get_memory_agent() -> MemoryAgent:
    """Get global memory agent."""
    global _memory_agent
    if _memory_agent is None:
        _memory_agent = MemoryAgent()
    return _memory_agent


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS MEMORY AGENT v1.0.0 ⚡              ║
╚═══════════════════════════════════════════════════════════╝
    """)
    agent = MemoryAgent()
    print(f"Memory ready: {agent.get_stats()}")
