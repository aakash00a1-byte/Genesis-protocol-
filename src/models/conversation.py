"""Genesis Protocol - Conversation Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

from genesis_protocol.models.message import Message


@dataclass
class ConversationContext:
    """
    Context information for a conversation.
    
    Contains conversation summary, key topics, and state.
    """
    summary: str = ""
    key_topics: List[str] = field(default_factory=list)
    user_intent: Optional[str] = None
    
    # State
    waiting_for_response: bool = False
    last_topic_change: datetime = field(default_factory=datetime.utcnow)
    
    # Memory references
    vector_memory_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """Convert context to dictionary."""
        return {
            "summary": self.summary,
            "key_topics": self.key_topics,
            "user_intent": self.user_intent,
            "waiting_for_response": self.waiting_for_response,
            "last_topic_change": self.last_topic_change.isoformat(),
            "vector_memory_ids": self.vector_memory_ids,
        }


@dataclass
class Conversation:
    """
    Conversation data model for Genesis Protocol.
    
    Represents a chat conversation with history and context.
    """
    id: str
    chat_id: int  # Telegram chat ID
    
    # History
    messages: List[Message] = field(default_factory=list)
    max_history: int = 100
    
    # Context
    context: ConversationContext = field(default_factory=ConversationContext)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    # State
    is_active: bool = True
    is_group: bool = False
    
    # Metadata
    title: Optional[str] = None
    language: str = "en"
    
    def to_dict(self) -> dict:
        """Convert conversation to dictionary."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "messages": [m.to_dict() for m in self.messages],
            "max_history": self.max_history,
            "context": self.context.to_dict(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "is_group": self.is_group,
            "title": self.title,
            "language": self.language,
        }
    
    def add_message(self, message: Message):
        """Add a message to the conversation."""
        self.messages.append(message)
        self.updated_at = datetime.utcnow()
        
        # Prune if exceeds max history
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """Get the most recent messages."""
        return self.messages[-count:] if self.messages else []
    
    def get_messages_for_ai(self, max_tokens: int = 8000) -> List[dict]:
        """
        Get messages formatted for AI processing.
        
        Args:
            max_tokens: Maximum tokens to include
            
        Returns:
            List of message dictionaries
        """
        result = []
        total_tokens = 0
        
        # Iterate from oldest to newest, keeping within token limit
        for message in reversed(self.messages):
            msg_dict = message.to_dict()
            # Rough estimate: 4 characters per token
            estimated_tokens = len(msg_dict.get("text", "")) // 4
            
            if total_tokens + estimated_tokens > max_tokens:
                break
                
            result.insert(0, msg_dict)
            total_tokens += estimated_tokens
        
        return result
    
    def update_context(self, summary: str = None, topics: List[str] = None):
        """Update conversation context."""
        if summary:
            self.context.summary = summary
        if topics:
            self.context.key_topics = topics
        self.context.last_topic_change = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def clear_history(self):
        """Clear conversation history."""
        self.messages = []
        self.context = ConversationContext()
        self.updated_at = datetime.utcnow()
    
    def get_message_count(self) -> int:
        """Get total message count."""
        return len(self.messages)