"""Genesis Protocol - Message Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class MessageType(Enum):
    """Types of messages supported by Genesis Protocol."""
    TEXT = "text"
    VOICE = "voice"
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    LOCATION = "location"
    STICKER = "sticker"
    COMMAND = "command"
    CALLBACK = "callback"


class MessageDirection(Enum):
    """Direction of message flow."""
    INCOMING = "incoming"    # From user to bot
    OUTGOING = "outgoing"    # From bot to user
    SYSTEM = "system"       # System messages


@dataclass
class Message:
    """
    Core message data model for Genesis Protocol.
    
    Represents a single message in a conversation, supporting
    text, voice, image, and other message types.
    """
    id: str
    chat_id: int
    user_id: int
    
    message_type: MessageType = MessageType.TEXT
    direction: MessageDirection = MessageDirection.INCOMING
    
    # Content
    text: Optional[str] = None
    voice_file_id: Optional[str] = None
    image_file_id: Optional[str] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reply_to_message_id: Optional[str] = None
    
    # AI related
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    tokens_used: Optional[int] = None
    latency_ms: Optional[int] = None
    
    # Processing
    processed: bool = False
    error: Optional[str] = None
    
    # Extra data
    metadata: dict = field(default_factory=dict)
    
    @classmethod
    def from_telegram_update(cls, update: dict, message_type: MessageType = MessageType.TEXT) -> "Message":
        """
        Create a Message from a Telegram update.
        
        Args:
            update: Telegram update dictionary
            message_type: Type of message
            
        Returns:
            Message: New message instance
        """
        message_data = update.get("message", update.get("edited_message", {}))
        
        return cls(
            id=str(message_data.get("message_id", "")),
            chat_id=message_data.get("chat", {}).get("id", 0),
            user_id=message_data.get("from", {}).get("id", 0),
            message_type=message_type,
            direction=MessageDirection.INCOMING,
            text=message_data.get("text"),
            timestamp=datetime.fromisoformat(
                message_data.get("date", datetime.utcnow().isoformat())
            ),
            metadata={
                "chat_username": message_data.get("chat", {}).get("username"),
                "chat_title": message_data.get("chat", {}).get("title"),
                "user_first_name": message_data.get("from", {}).get("first_name"),
                "user_last_name": message_data.get("from", {}).get("last_name"),
            }
        )
    
    def to_dict(self) -> dict:
        """Convert message to dictionary."""
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "message_type": self.message_type.value,
            "direction": self.direction.value,
            "text": self.text,
            "voice_file_id": self.voice_file_id,
            "image_file_id": self.image_file_id,
            "timestamp": self.timestamp.isoformat(),
            "reply_to_message_id": self.reply_to_message_id,
            "provider_used": self.provider_used,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "latency_ms": self.latency_ms,
            "processed": self.processed,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    def mark_processed(self, provider: str = None, model: str = None, 
                       tokens: int = None, latency: int = None):
        """Mark message as successfully processed."""
        self.processed = True
        self.provider_used = provider
        self.model_used = model
        self.tokens_used = tokens
        self.latency_ms = latency
        self.error = None
    
    def mark_failed(self, error: str):
        """Mark message processing as failed."""
        self.processed = False
        self.error = error