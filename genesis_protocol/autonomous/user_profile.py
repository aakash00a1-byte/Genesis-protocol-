"""User Profile - Genesis Protocol v1.3
Automatically learns user preferences and profile."""

import json
import re
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path


@dataclass
class UserProfile:
    """User profile with learned preferences."""
    user_id: int
    name: Optional[str] = None
    preferred_language: str = "en"
    favorite_topics: List[str] = field(default_factory=list)
    humor_level: float = 0.5  # 0.0 - 1.0
    conversation_style: str = "balanced"  # casual, formal, technical, friendly
    interaction_count: int = 0
    topics_mentioned: List[str] = field(default_factory=list)
    words_per_message_avg: float = 0.0
    prefers_concise: bool = False
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    learned_facts: List[str] = field(default_factory=list)
    
    def update_from_message(self, message: str):
        """Learn from user message."""
        self.interaction_count += 1
        self.last_seen = datetime.now()
        
        # Detect language (simple heuristic)
        hindi_words = ['kya', 'hai', 'nahi', 'batao', 'bol', 'acha', 'theek']
        if any(word in message.lower() for word in hindi_words):
            self.preferred_language = "hi"
        
        # Detect favorite topics
        topic_keywords = {
            'coding': ['code', 'python', 'javascript', 'programming', 'bug', 'function'],
            'music': ['song', 'music', 'band', 'singer', 'album'],
            'sports': ['cricket', 'football', 'game', 'match', 'player'],
            'movies': ['movie', 'film', 'actor', 'director', 'watch'],
            'tech': ['ai', 'computer', 'phone', 'app', 'software'],
            'food': ['food', 'eat', 'cook', 'recipe', 'restaurant'],
            'travel': ['travel', 'trip', 'flight', 'hotel', 'visit']
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in message.lower() for kw in keywords):
                if topic not in self.favorite_topics:
                    self.favorite_topics.append(topic)
        
        # Detect conversation style
        if any(word in message.lower() for word in ['lol', 'haha', '😄', 'bro', 'dude']):
            self.conversation_style = "casual"
        elif any(word in message.lower() for word in ['please', 'kindly', 'would', 'could']):
            self.conversation_style = "formal"
        elif any(word in message.lower() for word in ['code', 'error', 'debug', 'function']):
            self.conversation_style = "technical"
        
        # Detect humor preference
        if 'haha' in message.lower() or 'lol' in message.lower():
            self.humor_level = min(1.0, self.humor_level + 0.1)
        
        # Calculate words per message
        words = len(message.split())
        if self.words_per_message_avg == 0:
            self.words_per_message_avg = words
        else:
            self.words_per_message_avg = (self.words_per_message_avg + words) / 2
        
        # Detect preference for concise responses
        if len(message.split()) < 10:
            self.prefers_concise = True
    
    def add_learned_fact(self, fact: str):
        """Add a learned fact about the user."""
        if fact not in self.learned_facts:
            self.learned_facts.append(fact)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        data = asdict(self)
        data['first_seen'] = self.first_seen.isoformat()
        data['last_seen'] = self.last_seen.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, user_id: int, data: Dict[str, Any]) -> 'UserProfile':
        """Deserialize from dict."""
        data['user_id'] = user_id
        if 'first_seen' in data and isinstance(data['first_seen'], str):
            data['first_seen'] = datetime.fromisoformat(data['first_seen'])
        if 'last_seen' in data and isinstance(data['last_seen'], str):
            data['last_seen'] = datetime.fromisoformat(data['last_seen'])
        return cls(**data)


class UserProfileManager:
    """Manages user profiles with automatic learning."""
    
    def __init__(self, storage_path: str = "./data/profiles"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._profiles: Dict[int, UserProfile] = {}
    
    def _get_file_path(self, user_id: int) -> Path:
        """Get file path for user profile."""
        return self.storage_path / f"user_{user_id}.json"
    
    def get_profile(self, user_id: int) -> UserProfile:
        """Get or create user profile."""
        if user_id not in self._profiles:
            # Try to load from disk
            file_path = self._get_file_path(user_id)
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    self._profiles[user_id] = UserProfile.from_dict(user_id, data)
                except Exception:
                    self._profiles[user_id] = UserProfile(user_id=user_id)
            else:
                self._profiles[user_id] = UserProfile(user_id=user_id)
        
        return self._profiles[user_id]
    
    def save_profile(self, profile: UserProfile):
        """Save user profile to disk."""
        self._profiles[profile.user_id] = profile
        file_path = self._get_file_path(profile.user_id)
        with open(file_path, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)
    
    def learn_from_message(self, user_id: int, message: str):
        """Learn from user message."""
        profile = self.get_profile(user_id)
        profile.update_from_message(message)
        self.save_profile(profile)
        
        # Log the update
        try:
            from .event_system import get_event_logger, EventType
            events = get_event_logger()
            events.log(
                EventType.USER_PROFILE_UPDATED,
                f"Profile updated for user {user_id}",
                user_id=user_id,
                metadata={
                    'topics': profile.favorite_topics,
                    'style': profile.conversation_style
                }
            )
        except Exception:
            pass
    
    def get_conversation_context(self, user_id: int) -> str:
        """Get context string for conversation."""
        profile = self.get_profile(user_id)
        
        context_parts = []
        
        if profile.name:
            context_parts.append(f"User's name: {profile.name}")
        
        if profile.favorite_topics:
            topics = ", ".join(profile.favorite_topics[:3])
            context_parts.append(f"Interests: {topics}")
        
        if profile.preferred_language == "hi":
            context_parts.append("User prefers Hindi")
        
        context_parts.append(f"Style: {profile.conversation_style}")
        
        if profile.prefers_concise:
            context_parts.append("User prefers concise responses")
        
        if profile.learned_facts:
            facts = "; ".join(profile.learned_facts[:2])
            context_parts.append(f"Known facts: {facts}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def get_all_profiles(self) -> List[UserProfile]:
        """Get all user profiles."""
        return list(self._profiles.values())


# Global singleton
_profile_manager: Optional[UserProfileManager] = None


def get_user_profile_manager() -> UserProfileManager:
    """Get global user profile manager."""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = UserProfileManager()
    return _profile_manager
