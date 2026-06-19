"""Satisfaction System - Genesis Protocol v1.5
Tracks user satisfaction trends."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path


class SatisfactionLevel(Enum):
    """User satisfaction levels."""
    VERY_HAPPY = "very_happy"
    HAPPY = "happy"
    NEUTRAL = "neutral"
    UNHAPPY = "unhappy"
    FRUSTRATED = "frustrated"


class EmotionType(Enum):
    """Detected emotions."""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    EXCITED = "excited"
    FRUSTRATED = "frustrated"
    CONFUSED = "confused"


@dataclass
class SatisfactionSnapshot:
    """A satisfaction measurement."""
    level: SatisfactionLevel
    emotion: EmotionType
    detected_from: str  # message, feedback, implicit
    context: str
    timestamp: datetime


class SatisfactionTracker:
    """Tracks and predicts user satisfaction."""
    
    def __init__(self, storage_path: str = "./data/satisfaction"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._snapshots: List[SatisfactionSnapshot] = []
        self._load_snapshots()
    
    def _load_snapshots(self):
        """Load snapshots from disk."""
        sat_file = self.storage_path / "satisfaction.json"
        if sat_file.exists():
            try:
                with open(sat_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    item['level'] = SatisfactionLevel(item['level'])
                    item['emotion'] = EmotionType(item['emotion'])
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self._snapshots.append(SatisfactionSnapshot(**item))
            except Exception:
                pass
    
    def _save_snapshots(self):
        """Save snapshots to disk."""
        sat_file = self.storage_path / "satisfaction.json"
        data = [s.__dict__ for s in self._snapshots[-100:]]
        for d in data:
            if isinstance(d.get('timestamp'), datetime):
                d['timestamp'] = d['timestamp'].isoformat()
            d['level'] = d['level'].value
            d['emotion'] = d['emotion'].value
        try:
            with open(sat_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def detect_satisfaction(self, message: str = "", feedback: str = "", response: str = "") -> SatisfactionSnapshot:
        """Detect user satisfaction from message and feedback."""
        level = SatisfactionLevel.NEUTRAL
        emotion = EmotionType.NEUTRAL
        detected_from = "implicit"
        
        # Explicit feedback
        if feedback:
            detected_from = "feedback"
            feedback_lower = feedback.lower()
            if any(word in feedback_lower for word in ['perfect', 'amazing', 'best', 'love']):
                level = SatisfactionLevel.VERY_HAPPY
                emotion = EmotionType.EXCITED
            elif any(word in feedback_lower for word in ['great', 'thanks', 'good']):
                level = SatisfactionLevel.HAPPY
                emotion = EmotionType.POSITIVE
            elif any(word in feedback_lower for word in ['bad', 'wrong', 'terrible']):
                level = SatisfactionLevel.UNHAPPY
                emotion = EmotionType.FRUSTRATED
        
        # Implicit from message
        if level == SatisfactionLevel.NEUTRAL and message:
            detected_from = "implicit"
            message_lower = message.lower()
            
            # Positive indicators
            if any(word in message_lower for word in ['thanks', 'great', 'awesome', 'perfect', 'yay']):
                level = SatisfactionLevel.HAPPY
                emotion = EmotionType.POSITIVE
            elif any(word in message_lower for word in ['wow', 'omg', 'excited', 'cant wait']):
                level = SatisfactionLevel.VERY_HAPPY
                emotion = EmotionType.EXCITED
            
            # Negative indicators
            elif any(word in message_lower for word in ['wrong', 'fix', 'again', 'bad']):
                level = SatisfactionLevel.UNHAPPY
                emotion = EmotionType.FRUSTRATED
            elif any(word in message_lower for word in ['confused', 'dont understand', 'what', 'huh']):
                level = SatisfactionLevel.NEUTRAL
                emotion = EmotionType.CONFUSED
        
        snapshot = SatisfactionSnapshot(
            level=level,
            emotion=emotion,
            detected_from=detected_from,
            context=message[:50] if message else "",
            timestamp=datetime.now()
        )
        
        self._snapshots.append(snapshot)
        if len(self._snapshots) > 100:
            self._snapshots = self._snapshots[-100:]
        self._save_snapshots()
        
        return snapshot
    
    def get_current_level(self) -> SatisfactionLevel:
        """Get current satisfaction level (most recent)."""
        if not self._snapshots:
            return SatisfactionLevel.NEUTRAL
        return self._snapshots[-1].level
    
    def get_trend(self, hours: int = 24) -> str:
        """Get satisfaction trend over time period."""
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [s for s in self._snapshots if s.timestamp > cutoff]
        
        if len(recent) < 2:
            return "insufficient_data"
        
        # Count by level
        happy_count = sum(1 for s in recent if s.level in [
            SatisfactionLevel.HAPPY, SatisfactionLevel.VERY_HAPPY
        ])
        unhappy_count = sum(1 for s in recent if s.level in [
            SatisfactionLevel.UNHAPPY, SatisfactionLevel.FRUSTRATED
        ])
        
        total = len(recent)
        happy_ratio = happy_count / total
        
        if happy_ratio > 0.7:
            return "improving"
        elif happy_ratio < 0.4:
            return "declining"
        else:
            return "stable"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get satisfaction statistics."""
        if not self._snapshots:
            return {
                'current_level': 'neutral',
                'trend': 'insufficient_data',
                'total_measurements': 0
            }
        
        recent_24h = [s for s in self._snapshots 
                      if s.timestamp > datetime.now() - timedelta(hours=24)]
        
        level_counts = {
            'very_happy': 0, 'happy': 0, 'neutral': 0,
            'unhappy': 0, 'frustrated': 0
        }
        emotion_counts = {e.value: 0 for e in EmotionType}
        
        for s in recent_24h:
            level_counts[s.level.value] = level_counts.get(s.level.value, 0) + 1
            emotion_counts[s.emotion.value] = emotion_counts.get(s.emotion.value, 0) + 1
        
        return {
            'current_level': self.get_current_level().value,
            'trend': self.get_trend(),
            'total_measurements': len(self._snapshots),
            'last_24h': {
                'total': len(recent_24h),
                'levels': level_counts,
                'emotions': emotion_counts
            },
            'happiness_ratio': sum(1 for s in recent_24h if s.level in [
                SatisfactionLevel.HAPPY, SatisfactionLevel.VERY_HAPPY
            ]) / max(1, len(recent_24h))
        }


# Global singleton
_satisfaction_tracker: Optional[SatisfactionTracker] = None


def get_satisfaction_tracker() -> SatisfactionTracker:
    """Get global satisfaction tracker."""
    global _satisfaction_tracker
    if _satisfaction_tracker is None:
        _satisfaction_tracker = SatisfactionTracker()
    return _satisfaction_tracker
