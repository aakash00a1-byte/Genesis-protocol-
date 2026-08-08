"""Relationship Memory - GLUTTONY Presence Layer

Remembers creator name, preferences, long-term topics, and recurring patterns."""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class RelationshipMemory:
    """Persistent memory of relationship context with creator."""
    
    def __init__(self, storage_path: str = "data/relationship.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.creator_name: str = "Creator"
        self.preferences: Dict[str, Any] = {}
        self.long_term_topics: List[str] = []
        self.recurring_patterns: List[Dict] = []
        self.interaction_count: int = 0
        self.first_seen: Optional[str] = None
        self.last_seen: Optional[str] = None
        self.topics_history: List[Dict] = []
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load relationship memory from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.creator_name = data.get('creator_name', 'Creator')
                    self.preferences = data.get('preferences', {})
                    self.long_term_topics = data.get('long_term_topics', [])
                    self.recurring_patterns = data.get('recurring_patterns', [])
                    self.interaction_count = data.get('interaction_count', 0)
                    self.first_seen = data.get('first_seen')
                    self.last_seen = data.get('last_seen')
                    self.topics_history = data.get('topics_history', [])
            except Exception:
                pass
    
    def _save(self):
        """Save relationship memory to disk."""
        data = {
            'creator_name': self.creator_name,
            'preferences': self.preferences,
            'long_term_topics': self.long_term_topics,
            'recurring_patterns': self.recurring_patterns,
            'interaction_count': self.interaction_count,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'topics_history': self.topics_history,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def set_creator_name(self, name: str):
        """Set the creator's name."""
        if not self.first_seen:
            self.first_seen = datetime.now().isoformat()
        self.creator_name = name
        self._save()
    
    def record_preference(self, key: str, value: Any):
        """Record a preference."""
        self.preferences[key] = value
        self._save()
    
    def add_topic(self, topic: str, context: str = ""):
        """Add a long-term topic to remember."""
        topic_lower = topic.lower()
        if topic_lower not in [t['topic'].lower() for t in self.long_term_topics]:
            self.long_term_topics.append({
                'topic': topic,
                'context': context,
                'mentioned_at': datetime.now().isoformat(),
                'mention_count': 1
            })
        else:
            for t in self.long_term_topics:
                if t['topic'].lower() == topic_lower:
                    t['mention_count'] = t.get('mention_count', 0) + 1
                    break
        self._save()
    
    def add_pattern(self, pattern_type: str, description: str, 
                   frequency: int = 1) -> str:
        """Record a recurring pattern."""
        pattern = {
            'id': f"pat_{len(self.recurring_patterns)}_{int(datetime.now().timestamp())}",
            'type': pattern_type,
            'description': description,
            'frequency': frequency,
            'first_seen': datetime.now().isoformat(),
            'last_seen': datetime.now().isoformat()
        }
        self.recurring_patterns.append(pattern)
        self._save()
        return pattern['id']
    
    def record_interaction(self):
        """Record an interaction with the creator."""
        self.interaction_count += 1
        self.last_seen = datetime.now().isoformat()
        self._save()
    
    def add_topic_to_history(self, topic: str, message: str, 
                            response: str = ""):
        """Add a topic exchange to history."""
        self.topics_history.append({
            'topic': topic,
            'message': message,
            'response': response,
            'timestamp': datetime.now().isoformat()
        })
        # Keep only last 100
        if len(self.topics_history) > 100:
            self.topics_history = self.topics_history[-100:]
        self._save()
    
    def get_relationship_summary(self) -> Dict:
        """Get relationship summary."""
        return {
            'creator_name': self.creator_name,
            'interaction_count': self.interaction_count,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'topics_count': len(self.long_term_topics),
            'patterns_count': len(self.recurring_patterns)
        }
    
    def get_full_state(self) -> Dict:
        """Get complete relationship state for continuity."""
        return {
            'creator_name': self.creator_name,
            'preferences': self.preferences,
            'long_term_topics': self.long_term_topics,
            'recurring_patterns': self.recurring_patterns,
            'interaction_count': self.interaction_count,
            'first_seen': self.first_seen,
            'last_seen': self.last_seen,
            'topics_history': self.topics_history,
            'stats': self.get_relationship_summary()
        }
    
    def restore(self, state: Dict):
        """Restore relationship memory from state (continuity)."""
        self.creator_name = state.get('creator_name', 'Creator')
        self.preferences = state.get('preferences', {})
        self.long_term_topics = state.get('long_term_topics', [])
        self.recurring_patterns = state.get('recurring_patterns', [])
        self.interaction_count = state.get('interaction_count', 0)
        self.first_seen = state.get('first_seen')
        self.last_seen = state.get('last_seen')
        self.topics_history = state.get('topics_history', [])
        self._save()


_relationship_memory: Optional[RelationshipMemory] = None


def get_relationship_memory() -> RelationshipMemory:
    """Get relationship memory singleton."""
    global _relationship_memory
    if _relationship_memory is None:
        _relationship_memory = RelationshipMemory()
    return _relationship_memory
