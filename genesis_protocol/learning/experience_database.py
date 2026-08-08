"""Experience Database - Genesis Protocol v1.5
Stores successful/failed interactions, summaries, and lessons learned."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class ExperienceType(Enum):
    """Types of experiences."""
    SUCCESS = "success"
    FAILURE = "failure"
    LESSON = "lesson"
    INSIGHT = "insight"
    SUMMARIZATION = "summarization"


@dataclass
class Experience:
    """An experience record."""
    id: str
    experience_type: ExperienceType
    title: str
    description: str
    context: str  # What was being discussed
    outcome: str  # What happened
    lessons: List[str]  # What was learned
    timestamp: datetime
    conversation_count: int = 0
    quality_score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'type': self.experience_type.value,
            'title': self.title,
            'description': self.description,
            'context': self.context,
            'outcome': self.outcome,
            'lessons': self.lessons,
            'timestamp': self.timestamp.isoformat(),
            'conversation_count': self.conversation_count,
            'quality_score': self.quality_score
        }


class ExperienceDatabase:
    """Stores and retrieves experiences."""
    
    def __init__(self, storage_path: str = "./data/experiences"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._experiences: List[Experience] = []
        self._experience_counter = 0
        self._load_experiences()
    
    def _load_experiences(self):
        """Load experiences from disk."""
        exp_file = self.storage_path / "experiences.json"
        if exp_file.exists():
            try:
                with open(exp_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    item['experience_type'] = ExperienceType(item['type'])
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self._experiences.append(Experience(**item))
            except Exception:
                pass
    
    def _save_experiences(self):
        """Save experiences to disk."""
        exp_file = self.storage_path / "experiences.json"
        data = [e.to_dict() for e in self._experiences[-200:]]  # Keep last 200
        try:
            with open(exp_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def add_experience(
        self,
        exp_type: ExperienceType,
        title: str,
        description: str,
        context: str = "",
        outcome: str = "",
        lessons: List[str] = None,
        quality_score: float = 0.0
    ) -> Experience:
        """Add a new experience."""
        self._experience_counter += 1
        exp_id = f"exp_{self._experience_counter}_{datetime.now().strftime('%Y%m%d')}"
        
        experience = Experience(
            id=exp_id,
            experience_type=exp_type,
            title=title,
            description=description,
            context=context,
            outcome=outcome,
            lessons=lessons or [],
            timestamp=datetime.now(),
            conversation_count=self._experience_counter,
            quality_score=quality_score
        )
        
        self._experiences.append(experience)
        if len(self._experiences) > 200:
            self._experiences = self._experiences[-200:]
        self._save_experiences()
        
        return experience
    
    def add_success(self, title: str, description: str, context: str = "", quality_score: float = 1.0):
        """Add a successful experience."""
        return self.add_experience(
            ExperienceType.SUCCESS, title, description, context,
            outcome="Success", lessons=["This approach worked well"],
            quality_score=quality_score
        )
    
    def add_failure(self, title: str, description: str, context: str = "", lessons: List[str] = None):
        """Add a failed experience."""
        return self.add_experience(
            ExperienceType.FAILURE, title, description, context,
            outcome="Failed", lessons=lessons or ["Need to try a different approach"],
            quality_score=0.0
        )
    
    def add_lesson(self, title: str, lesson: str, context: str = ""):
        """Add a learned lesson."""
        return self.add_experience(
            ExperienceType.LESSON, title, "", context,
            outcome="Lesson learned",
            lessons=[lesson],
            quality_score=0.5
        )
    
    def get_recent(self, limit: int = 20) -> List[Experience]:
        """Get recent experiences."""
        return self._experiences[-limit:]
    
    def get_by_type(self, exp_type: ExperienceType, limit: int = 20) -> List[Experience]:
        """Get experiences by type."""
        filtered = [e for e in self._experiences if e.experience_type == exp_type]
        return filtered[-limit:]
    
    def get_success_rate(self) -> float:
        """Get overall success rate."""
        if not self._experiences:
            return 0.0
        successes = sum(1 for e in self._experiences if e.experience_type == ExperienceType.SUCCESS)
        return successes / len(self._experiences)
    
    def get_lessons_learned(self, limit: int = 10) -> List[str]:
        """Get all unique lessons learned."""
        lessons = []
        for exp in self._experiences:
            for lesson in exp.lessons:
                if lesson not in lessons:
                    lessons.append(lesson)
        return lessons[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get experience statistics."""
        if not self._experiences:
            return {'total': 0}
        
        return {
            'total_experiences': len(self._experiences),
            'success_count': sum(1 for e in self._experiences if e.experience_type == ExperienceType.SUCCESS),
            'failure_count': sum(1 for e in self._experiences if e.experience_type == ExperienceType.FAILURE),
            'lesson_count': sum(1 for e in self._experiences if e.experience_type == ExperienceType.LESSON),
            'success_rate': self.get_success_rate(),
            'unique_lessons': len(self.get_lessons_learned())
        }


# Global singleton
_experience_database: Optional[ExperienceDatabase] = None


def get_experience_database() -> ExperienceDatabase:
    """Get global experience database."""
    global _experience_database
    if _experience_database is None:
        _experience_database = ExperienceDatabase()
    return _experience_database
