"""Memory Summarizer - Genesis Protocol v1.1"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from .long_term_memory import LongTermMemory, MemoryEntry, MemoryImportance


class MemorySummarizer:
    """Summarizes conversation history for compact memory."""
    
    def __init__(self, long_term_memory: LongTermMemory = None):
        self.ltm = long_term_memory or LongTermMemory()
    
    def summarize_conversation(
        self,
        messages: List[Dict[str, str]],
        user_id: int
    ) -> str:
        """Create a summary of conversation messages."""
        if not messages:
            return ""
        
        # Extract key information
        user_messages = [m['content'] for m in messages if m.get('role') == 'user']
        assistant_messages = [m['content'] for m in messages if m.get('role') == 'assistant']
        
        # Create summary
        summary_parts = []
        
        if user_messages:
            summary_parts.append(
                f"User discussed: {', '.join(user_messages[:3])}"
            )
        
        if assistant_messages:
            summary_parts.append(
                f"Assistant responded with information about: {', '.join(assistant_messages[:2])}"
            )
        
        return "; ".join(summary_parts)
    
    def store_summary(
        self,
        summary: str,
        user_id: int,
        context: str = ""
    ) -> str:
        """Store a conversation summary in long-term memory."""
        if not summary:
            return None
        
        full_content = summary
        if context:
            full_content = f"{context}\n\n{summary}"
        
        return self.ltm.add_memory(
            content=full_content,
            user_id=user_id,
            importance=MemoryImportance.MEDIUM,
            category="summary"
        )
    
    def get_context_for_new_conversation(
        self,
        user_id: int,
        current_topic: str = "",
        limit: int = 5
    ) -> str:
        """Get relevant context for starting a new conversation."""
        memories = []
        
        # If we have a current topic, search for related memories
        if current_topic:
            related = self.ltm.search(
                query=current_topic,
                user_id=user_id,
                limit=limit
            )
            memories.extend(related)
        
        # Get recent important memories
        recent = self.ltm.get_recent(
            user_id=user_id,
            limit=limit,
            category="summary"
        )
        memories.extend(recent)
        
        # Get user facts
        facts = self.ltm.search(
            query="user preference important fact",
            user_id=user_id,
            limit=3,
            min_importance=MemoryImportance.HIGH
        )
        memories.extend(facts)
        
        # Remove duplicates and sort by importance
        seen = set()
        unique_memories = []
        for m in memories:
            if m.id not in seen:
                seen.add(m.id)
                unique_memories.append(m)
        
        unique_memories.sort(
            key=lambda x: (x.importance.value, x.last_accessed.timestamp()),
            reverse=True
        )
        
        # Format as context
        context_parts = []
        for memory in unique_memories[:limit]:
            context_parts.append(f"- {memory.content}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def should_create_summary(self, message_count: int) -> bool:
        """Determine if we should create a summary."""
        # Create summary every 20 messages
        return message_count > 0 and message_count % 20 == 0
