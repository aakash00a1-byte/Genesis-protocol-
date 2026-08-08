"""Unified Context Manager - Genesis Protocol v1.4
Merges persona, mood, profile, history, memory, tasks into one context object."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ConversationMessage:
    """A message in the conversation history."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TaskContext:
    """Context about a task."""
    id: str
    name: str
    description: str
    status: str
    created_at: datetime


@dataclass
class MemoryContext:
    """Context about a memory entry."""
    id: str
    content: str
    importance: int
    category: str
    created_at: datetime


@dataclass
class UnifiedContext:
    """Unified context object for AI responses."""
    
    # User info
    user_id: int
    user_name: Optional[str] = None
    
    # Personality
    persona: str = "normal"
    persona_config: Dict[str, float] = field(default_factory=lambda: {
        'humor': 0.3, 'formality': 0.5, 'empathy': 0.7
    })
    
    # Mood
    mood: str = "calm"
    mood_style: str = "serene"
    
    # User profile
    preferred_language: str = "en"
    favorite_topics: List[str] = field(default_factory=list)
    conversation_style: str = "balanced"
    learned_facts: List[str] = field(default_factory=list)
    
    # Conversation history (recent messages)
    recent_messages: List[ConversationMessage] = field(default_factory=list)
    
    # Long-term memories (relevant to current conversation)
    relevant_memories: List[MemoryContext] = field(default_factory=list)
    
    # Active tasks
    pending_tasks: List[TaskContext] = field(default_factory=list)
    completed_tasks: List[TaskContext] = field(default_factory=list)
    
    # Session info
    session_id: Optional[str] = None
    session_start: datetime = field(default_factory=datetime.now)
    
    # Metadata
    conversation_count: int = 0
    last_interaction: datetime = field(default_factory=datetime.now)
    
    def to_prompt_context(self) -> str:
        """Convert to a string for AI prompt injection."""
        parts = []
        
        # User info
        if self.user_name:
            parts.append(f"User's name: {self.user_name}")
        
        # Language
        if self.preferred_language == "hi":
            parts.append("User prefers Hindi responses")
        
        # Persona
        parts.append(f"Current persona: {self.persona} (humor={self.persona_config.get('humor', 0.5)})")
        
        # Mood
        parts.append(f"Current mood: {self.mood} - {self.mood_style}")
        
        # Topics
        if self.favorite_topics:
            parts.append(f"User interests: {', '.join(self.favorite_topics[:5])}")
        
        # Learned facts
        if self.learned_facts:
            parts.append(f"Important facts: {'; '.join(self.learned_facts[:3])}")
        
        # Active tasks
        if self.pending_tasks:
            task_names = [t.name for t in self.pending_tasks[:3]]
            parts.append(f"Pending tasks: {', '.join(task_names)}")
        
        # Relevant memories
        if self.relevant_memories:
            mem_contents = [m.content[:50] for m in self.relevant_memories[:2]]
            parts.append(f"Relevant memories: {'; '.join(mem_contents)}")
        
        # Conversation style
        parts.append(f"Conversation style: {self.conversation_style}")
        
        return "\n".join(parts)
    
    def add_message(self, role: str, content: str):
        """Add a message to conversation history."""
        self.recent_messages.append(ConversationMessage(role=role, content=content))
        self.last_interaction = datetime.now()
        
        # Keep only recent messages
        if len(self.recent_messages) > 20:
            self.recent_messages = self.recent_messages[-20:]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            'user_id': self.user_id,
            'user_name': self.user_name,
            'persona': self.persona,
            'mood': self.mood,
            'preferred_language': self.preferred_language,
            'favorite_topics': self.favorite_topics,
            'conversation_style': self.conversation_style,
            'learned_facts': self.learned_facts,
            'pending_tasks_count': len(self.pending_tasks),
            'relevant_memories_count': len(self.relevant_memories),
            'recent_messages_count': len(self.recent_messages),
            'session_id': self.session_id,
            'session_start': self.session_start.isoformat(),
            'conversation_count': self.conversation_count
        }


class ContextManager:
    """Manages unified context for each user."""
    
    def __init__(self):
        self._contexts: Dict[int, UnifiedContext] = {}
    
    def get_context(self, user_id: int) -> UnifiedContext:
        """Get or create context for user."""
        if user_id not in self._contexts:
            self._contexts[user_id] = UnifiedContext(user_id=user_id)
        
        ctx = self._contexts[user_id]
        
        # Refresh context from sources
        self._refresh_context(ctx)
        
        return ctx
    
    def _refresh_context(self, ctx: UnifiedContext):
        """Refresh context from all sources."""
        # Get persona from personality engine
        try:
            from genesis_protocol.personality import get_personality_engine
            engine = get_personality_engine(ctx.user_id)
            ctx.persona = engine.current_persona.value
            ctx.persona_config = engine.get_persona_config()
        except Exception:
            pass
        
        # Get mood from mood engine
        try:
            from genesis_protocol.autonomous import get_mood_engine, Mood
            mood_engine = get_mood_engine(ctx.user_id)
            ctx.mood = mood_engine.current_mood.value
            ctx.mood_style = mood_engine.MOOD_CONFIGS[mood_engine.current_mood].response_style
        except Exception:
            pass
        
        # Get user profile
        try:
            from genesis_protocol.autonomous import get_user_profile_manager
            profile_mgr = get_user_profile_manager()
            profile = profile_mgr.get_profile(ctx.user_id)
            ctx.user_name = profile.name
            ctx.preferred_language = profile.preferred_language
            ctx.favorite_topics = profile.favorite_topics
            ctx.conversation_style = profile.conversation_style
            ctx.learned_facts = profile.learned_facts
        except Exception:
            pass
        
        # Get pending tasks
        try:
            from genesis_protocol.tasks import TaskQueue, TaskStatus
            queue = TaskQueue()
            all_tasks = queue.get_user_tasks(ctx.user_id)
            ctx.pending_tasks = [
                TaskContext(
                    id=str(t.id),
                    name=t.name,
                    description=t.description or "",
                    status=t.status.value,
                    created_at=t.created_at
                )
                for t in all_tasks
                if t.status == TaskStatus.PENDING
            ]
        except Exception:
            pass
        
        # Get relevant memories
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            # Get recent important memories
            recent = ltm.get_recent(ctx.user_id, limit=5)
            ctx.relevant_memories = [
                MemoryContext(
                    id=m.id,
                    content=m.content,
                    importance=m.importance.value if hasattr(m.importance, 'value') else m.importance,
                    category=m.category or "general",
                    created_at=m.created_at
                )
                for m in recent
            ]
        except Exception:
            pass
    
    def clear_context(self, user_id: int):
        """Clear context for user."""
        if user_id in self._contexts:
            del self._contexts[user_id]
    
    def get_all_contexts(self) -> List[UnifiedContext]:
        """Get all active contexts."""
        return list(self._contexts.values())


# Global singleton
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get global context manager."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
