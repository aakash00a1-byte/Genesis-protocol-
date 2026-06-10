"""Genesis Protocol - User Data Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class UserPreferences:
    """User preferences for Genesis Protocol."""
    language: str = "en"
    response_style: str = "detailed"  # concise | detailed | technical
    voice_enabled: bool = False
    image_analysis_enabled: bool = True
    web_search_enabled: bool = True
    
    # AI provider preferences
    preferred_provider: Optional[str] = None
    
    # Notification settings
    notify_on_processed: bool = True
    
    def to_dict(self) -> dict:
        """Convert preferences to dictionary."""
        return {
            "language": self.language,
            "response_style": self.response_style,
            "voice_enabled": self.voice_enabled,
            "image_analysis_enabled": self.image_analysis_enabled,
            "web_search_enabled": self.web_search_enabled,
            "preferred_provider": self.preferred_provider,
            "notify_on_processed": self.notify_on_processed,
        }


@dataclass
class UserStats:
    """User usage statistics."""
    total_messages: int = 0
    total_tokens_used: int = 0
    total_cost: float = 0.0
    
    messages_today: int = 0
    tokens_today: int = 0
    
    last_message_time: Optional[datetime] = None
    first_seen: datetime = field(default_factory=datetime.utcnow)
    
    # Provider usage counts
    groq_messages: int = 0
    openai_messages: int = 0
    gemini_messages: int = 0
    huggingface_messages: int = 0
    
    def to_dict(self) -> dict:
        """Convert stats to dictionary."""
        return {
            "total_messages": self.total_messages,
            "total_tokens_used": self.total_tokens_used,
            "total_cost": self.total_cost,
            "messages_today": self.messages_today,
            "tokens_today": self.tokens_today,
            "last_message_time": self.last_message_time.isoformat() if self.last_message_time else None,
            "first_seen": self.first_seen.isoformat(),
            "groq_messages": self.groq_messages,
            "openai_messages": self.openai_messages,
            "gemini_messages": self.gemini_messages,
            "huggingface_messages": self.huggingface_messages,
        }
    
    def record_message(self, provider: str, tokens: int, cost: float):
        """Record a processed message."""
        self.total_messages += 1
        self.total_tokens_used += tokens
        self.total_cost += cost
        self.messages_today += 1
        self.tokens_today += tokens
        self.last_message_time = datetime.utcnow()
        
        # Track provider usage
        if provider == "groq":
            self.groq_messages += 1
        elif provider == "openai":
            self.openai_messages += 1
        elif provider == "gemini":
            self.gemini_messages += 1
        elif provider == "huggingface":
            self.huggingface_messages += 1


@dataclass
class User:
    """
    User data model for Genesis Protocol.
    
    Represents a Telegram user with their preferences and statistics.
    """
    id: int  # Telegram user ID
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    
    # Status
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    
    # Settings
    preferences: UserPreferences = field(default_factory=UserPreferences)
    stats: UserStats = field(default_factory=UserStats)
    
    # Security
    blocked: bool = False
    blocked_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert user to dictionary."""
        return {
            "id": self.id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "preferences": self.preferences.to_dict(),
            "stats": self.stats.to_dict(),
            "blocked": self.blocked,
            "blocked_reason": self.blocked_reason,
        }
    
    @classmethod
    def from_telegram_user(cls, tg_user: dict) -> "User":
        """
        Create a User from a Telegram user object.
        
        Args:
            tg_user: Telegram user dictionary
            
        Returns:
            User: New user instance
        """
        return cls(
            id=tg_user.get("id", 0),
            username=tg_user.get("username"),
            first_name=tg_user.get("first_name"),
            last_name=tg_user.get("last_name"),
        )
    
    def update_last_seen(self):
        """Update last seen timestamp."""
        self.last_seen = datetime.utcnow()
    
    def is_blocked(self) -> bool:
        """Check if user is blocked."""
        return self.blocked