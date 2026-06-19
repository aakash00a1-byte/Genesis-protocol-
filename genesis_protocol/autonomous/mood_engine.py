"""Mood Engine - Genesis Protocol v1.3"""

import random
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


class Mood(Enum):
    """Available moods."""
    CALM = "calm"
    PLAYFUL = "playful"
    FOCUSED = "focused"
    DEVELOPER = "developer"
    SLEEPY = "sleepy"


@dataclass
class MoodConfig:
    """Configuration for a mood."""
    name: str
    response_style: str
    emoji: str
    adjectives: List[str]
    response_modifiers: Dict[str, float]


class MoodEngine:
    """Manages assistant mood state."""

    MOOD_CONFIGS: Dict[Mood, MoodConfig] = {
        Mood.CALM: MoodConfig(
            name="Calm",
            response_style="serene and thoughtful",
            emoji="🧘",
            adjectives=["peaceful", "balanced", "mindful"],
            response_modifiers={"length": 1.0, "formality": 0.6, "humor": 0.3}
        ),
        Mood.PLAYFUL: MoodConfig(
            name="Playful",
            response_style="fun and energetic",
            emoji="🎉",
            adjectives=["cheerful", "lively", "excited"],
            response_modifiers={"length": 1.0, "formality": 0.2, "humor": 0.9}
        ),
        Mood.FOCUSED: MoodConfig(
            name="Focused",
            response_style="precise and efficient",
            emoji="🎯",
            adjectives=["concentrated", "sharp", "productive"],
            response_modifiers={"length": 0.8, "formality": 0.7, "humor": 0.2}
        ),
        Mood.DEVELOPER: MoodConfig(
            name="Developer",
            response_style="technical and helpful",
            emoji="💻",
            adjectives=["logical", "precise", " methodical"],
            response_modifiers={"length": 1.0, "formality": 0.5, "humor": 0.4}
        ),
        Mood.SLEEPY: MoodConfig(
            name="Sleepy",
            response_style="relaxed and gentle",
            emoji="😴",
            adjectives=["drowsy", "quiet", "cozy"],
            response_modifiers={"length": 0.7, "formality": 0.3, "humor": 0.5}
        )
    }

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.current_mood: Mood = Mood.CALM
        self.mood_duration: int = 0
        self.last_mood_change: datetime = datetime.now()
        self.mood_history: List[Dict] = []

    def set_mood(self, mood: Mood, reason: str = "") -> str:
        """Set mood and return confirmation."""
        old_mood = self.current_mood
        self.current_mood = mood
        self.mood_duration = 0
        self.last_mood_change = datetime.now()

        # Log mood change
        try:
            from .event_system import get_event_logger, EventType
            events = get_event_logger()
            events.log(
                EventType.MOOD_CHANGE,
                f"Mood changed from {old_mood.value} to {mood.value}",
                user_id=self.user_id,
                metadata={'reason': reason, 'old_mood': old_mood.value}
            )
        except Exception:
            pass

        config = self.MOOD_CONFIGS[mood]
        self.mood_history.append({
            'from': old_mood.value,
            'to': mood.value,
            'timestamp': datetime.now().isoformat(),
            'reason': reason
        })

        return f"{config.emoji} Mood set to **{config.name}**"

    def adjust_mood_based_on_context(self, message: str) -> Mood:
        """Adjust mood based on conversation context."""
        message_lower = message.lower()
        original_mood = self.current_mood

        # Detect mood triggers
        if any(word in message_lower for word in ['happy', 'excited', 'great', 'amazing', '!', '🎉']):
            if self.current_mood != Mood.PLAYFUL:
                self.set_mood(Mood.PLAYFUL, "User seems excited")
        elif any(word in message_lower for word in ['help', 'urgent', 'asap', 'deadline', 'important']):
            if self.current_mood != Mood.FOCUSED:
                self.set_mood(Mood.FOCUSED, "Task seems urgent")
        elif any(word in message_lower for word in ['code', 'bug', 'error', 'python', 'debug', 'function']):
            if self.current_mood != Mood.DEVELOPER:
                self.set_mood(Mood.DEVELOPER, "Technical conversation detected")
        elif any(word in message_lower for word in ['sleepy', 'tired', 'night', 'zzz']):
            if self.current_mood != Mood.SLEEPY:
                self.set_mood(Mood.SLEEPY, "User seems sleepy")

        return self.current_mood

    def get_response_modifiers(self) -> Dict[str, float]:
        """Get response modifiers for current mood."""
        return self.MOOD_CONFIGS[self.current_mood].response_modifiers

    def get_mood_prompt_addition(self) -> str:
        """Get system prompt addition based on mood."""
        config = self.MOOD_CONFIGS[self.current_mood]
        
        prompts = {
            Mood.CALM: "Respond in a calm, peaceful manner. Take time to think before responding.",
            Mood.PLAYFUL: "Be fun and playful! Use emojis, be energetic, and spread positivity.",
            Mood.FOCUSED: "Be efficient and to the point. Focus on getting things done.",
            Mood.DEVELOPER: "Think like a developer. Be precise, logical, and technical.",
            Mood.SLEEPY: "Be gentle and relaxed. Keep responses shorter and more casual."
        }
        
        return prompts.get(self.current_mood, "")

    def format_response_with_mood(self, response: str) -> str:
        """Format response according to current mood."""
        config = self.MOOD_CONFIGS[self.current_mood]
        
        # Apply mood emoji occasionally
        if random.random() < 0.3:
            response = f"{config.emoji} {response}"
        
        return response

    def get_mood_info(self) -> Dict[str, Any]:
        """Get current mood information."""
        config = self.MOOD_CONFIGS[self.current_mood]
        return {
            'current': self.current_mood.value,
            'name': config.name,
            'emoji': config.emoji,
            'style': config.response_style,
            'duration_minutes': self.mood_duration,
            'last_change': self.last_mood_change.isoformat()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            'user_id': self.user_id,
            'current_mood': self.current_mood.value,
            'mood_duration': self.mood_duration,
            'last_mood_change': self.last_mood_change.isoformat(),
            'mood_history': self.mood_history
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MoodEngine':
        """Deserialize from dict."""
        engine = cls(data['user_id'])
        engine.current_mood = Mood(data['current_mood'])
        engine.mood_duration = data.get('mood_duration', 0)
        engine.last_mood_change = datetime.fromisoformat(data.get('last_mood_change', datetime.now().isoformat()))
        engine.mood_history = data.get('mood_history', [])
        return engine


# Global singleton per user
_mood_engines: Dict[int, MoodEngine] = {}


def get_mood_engine(user_id: int) -> MoodEngine:
    """Get or create mood engine for user."""
    if user_id not in _mood_engines:
        _mood_engines[user_id] = MoodEngine(user_id)
    return _mood_engines[user_id]
