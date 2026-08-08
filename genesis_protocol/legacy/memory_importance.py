"""Memory Importance - GLUTTONY Legacy

Ranks memories: temporary, important, core, permanent.
Prevents important memories from being lost."""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path


class MemoryRank(Enum):
    """Memory importance ranks."""
    TEMPORARY = "temporary"      # Short-term, can be forgotten
    IMPORTANT = "important"      # Significant, keep longer
    CORE = "core"                # Core identity, protect
    PERMANENT = "permanent"      # Never delete


class MemoryImportance:
    """Memory importance ranking system."""
    
    # Default retention periods (days)
    RETENTION_PERIODS = {
        MemoryRank.TEMPORARY: 1,
        MemoryRank.IMPORTANT: 30,
        MemoryRank.CORE: 365,
        MemoryRank.PERMANENT: None  # Never expires
    }
    
    # Protection levels
    PROTECTION_LEVELS = {
        MemoryRank.TEMPORARY: 0,
        MemoryRank.IMPORTANT: 1,
        MemoryRank.CORE: 2,
        MemoryRank.PERMANENT: 3
    }
    
    def __init__(self, storage_path: str = "data/legacy/memory_importance.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        
        # memories: id -> {rank, content, created_at, last_accessed, access_count, protected}
        self.memories: Dict[str, Dict] = {}
        
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load memory importance from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.memories = data.get('memories', {})
            except Exception:
                pass
    
    def _save(self):
        """Save memory importance to disk."""
        data = {
            'memories': self.memories,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def register_memory(self, memory_id: str, content: str = "",
                       rank: MemoryRank = MemoryRank.IMPORTANT) -> str:
        """Register a memory with a rank."""
        if memory_id in self.memories:
            return memory_id
        
        self.memories[memory_id] = {
            'id': memory_id,
            'content': content[:500] if content else "",  # Store preview
            'rank': rank.value,
            'created_at': datetime.now().isoformat(),
            'last_accessed': datetime.now().isoformat(),
            'access_count': 0,
            'protected': rank in [MemoryRank.CORE, MemoryRank.PERMANENT]
        }
        
        self._save()
        return memory_id
    
    def set_rank(self, memory_id: str, rank: MemoryRank) -> bool:
        """Change memory rank."""
        if memory_id not in self.memories:
            return False
        
        self.memories[memory_id]['rank'] = rank.value
        self.memories[memory_id]['protected'] = rank in [MemoryRank.CORE, MemoryRank.PERMANENT]
        self._save()
        return True
    
    def promote(self, memory_id: str) -> bool:
        """Promote memory to higher rank."""
        if memory_id not in self.memories:
            return False
        
        current_rank = MemoryRank(self.memories[memory_id]['rank'])
        
        if current_rank == MemoryRank.TEMPORARY:
            return self.set_rank(memory_id, MemoryRank.IMPORTANT)
        elif current_rank == MemoryRank.IMPORTANT:
            return self.set_rank(memory_id, MemoryRank.CORE)
        elif current_rank == MemoryRank.CORE:
            return self.set_rank(memory_id, MemoryRank.PERMANENT)
        
        return False  # Already PERMANENT
    
    def demote(self, memory_id: str) -> bool:
        """Demote memory to lower rank."""
        if memory_id not in self.memories:
            return False
        
        current_rank = MemoryRank(self.memories[memory_id]['rank'])
        
        if current_rank == MemoryRank.PERMANENT:
            return self.set_rank(memory_id, MemoryRank.CORE)
        elif current_rank == MemoryRank.CORE:
            return self.set_rank(memory_id, MemoryRank.IMPORTANT)
        elif current_rank == MemoryRank.IMPORTANT:
            return self.set_rank(memory_id, MemoryRank.TEMPORARY)
        
        return False  # Already TEMPORARY
    
    def access_memory(self, memory_id: str):
        """Record memory access."""
        if memory_id in self.memories:
            self.memories[memory_id]['last_accessed'] = datetime.now().isoformat()
            self.memories[memory_id]['access_count'] += 1
            self._save()
    
    def is_protected(self, memory_id: str) -> bool:
        """Check if memory is protected from deletion."""
        if memory_id not in self.memories:
            return False
        return self.memories[memory_id].get('protected', False)
    
    def get_memories_by_rank(self, rank: MemoryRank) -> List[Dict]:
        """Get all memories of a specific rank."""
        return [m for m in self.memories.values() if m['rank'] == rank.value]
    
    def get_protected_memories(self) -> List[Dict]:
        """Get all protected memories."""
        return [m for m in self.memories.values() if m.get('protected', False)]
    
    def get_expired_memories(self) -> List[str]:
        """Get memory IDs that have expired (temporary only)."""
        expired = []
        now = datetime.now()
        
        for mem_id, mem in self.memories.items():
            if mem.get('protected', False):
                continue
            
            if mem['rank'] == MemoryRank.TEMPORARY.value:
                created = datetime.fromisoformat(mem['created_at'])
                if (now - created).days >= self.RETENTION_PERIODS[MemoryRank.TEMPORARY]:
                    expired.append(mem_id)
        
        return expired
    
    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory if not protected."""
        if memory_id not in self.memories:
            return False
        
        if self.is_protected(memory_id):
            return False
        
        del self.memories[memory_id]
        self._save()
        return True
    
    def get_stats(self) -> Dict:
        """Get memory importance statistics."""
        stats = {
            'total_memories': len(self.memories),
            'by_rank': {},
            'protected_count': sum(1 for m in self.memories.values() if m.get('protected', False)),
            'expired_count': len(self.get_expired_memories())
        }
        
        for rank in MemoryRank:
            count = sum(1 for m in self.memories.values() if m['rank'] == rank.value)
            stats['by_rank'][rank.value] = count
        
        return stats
    
    def get_all(self) -> Dict:
        """Get all memory importance data."""
        return {
            'memories': self.memories,
            'stats': self.get_stats()
        }


_memory_importance: Optional[MemoryImportance] = None


def get_memory_importance() -> MemoryImportance:
    """Get memory importance singleton."""
    global _memory_importance
    if _memory_importance is None:
        _memory_importance = MemoryImportance()
    return _memory_importance
