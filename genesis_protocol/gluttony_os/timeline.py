"""Timeline Memory - GLUTTONY Presence Layer

Remembers important conversations, milestones, recoveries, lessons, and relationship history."""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class TimelineMemory:
    """Persistent memory of important events and milestones."""
    
    def __init__(self, storage_path: str = "data/timeline.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.events: List[Dict] = []
        self.milestones: List[Dict] = []
        self.lessons: List[Dict] = []
        self.recoveries: List[Dict] = []
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load timeline from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.events = data.get('events', [])
                    self.milestones = data.get('milestones', [])
                    self.lessons = data.get('lessons', [])
                    self.recoveries = data.get('recoveries', [])
            except Exception:
                self._init_empty()
    
    def _save(self):
        """Save timeline to disk."""
        data = {
            'events': self.events,
            'milestones': self.milestones,
            'lessons': self.lessons,
            'recoveries': self.recoveries,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _init_empty(self):
        """Initialize empty timeline."""
        self.events = []
        self.milestones = []
        self.lessons = []
        self.recoveries = []
    
    def add_event(self, event_type: str, title: str, description: str, 
                  metadata: Dict = None) -> str:
        """Add an important event."""
        event = {
            'id': f"evt_{len(self.events)}_{int(datetime.now().timestamp())}",
            'type': event_type,
            'title': title,
            'description': description,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        self.events.append(event)
        self._save()
        return event['id']
    
    def add_milestone(self, title: str, description: str, 
                     category: str = "general") -> str:
        """Record a milestone achievement."""
        milestone = {
            'id': f"ms_{len(self.milestones)}_{int(datetime.now().timestamp())}",
            'title': title,
            'description': description,
            'category': category,
            'achieved_at': datetime.now().isoformat()
        }
        self.milestones.append(milestone)
        self.add_event('milestone', title, description, {'category': category})
        self._save()
        return milestone['id']
    
    def add_recovery(self, failure_context: str, recovery_method: str,
                     lessons_learned: str) -> str:
        """Record a recovery from failure."""
        recovery = {
            'id': f"rec_{len(self.recoveries)}_{int(datetime.now().timestamp())}",
            'failure_context': failure_context,
            'recovery_method': recovery_method,
            'lessons_learned': lessons_learned,
            'recovered_at': datetime.now().isoformat()
        }
        self.recoveries.append(recovery)
        self.add_event('recovery', 'Recovery', failure_context, {
            'method': recovery_method,
            'lessons': lessons_learned
        })
        self._save()
        return recovery['id']
    
    def add_lesson(self, category: str, lesson: str, 
                   context: str = "") -> str:
        """Record an important lesson."""
        lesson_entry = {
            'id': f"les_{len(self.lessons)}_{int(datetime.now().timestamp())}",
            'category': category,
            'lesson': lesson,
            'context': context,
            'learned_at': datetime.now().isoformat()
        }
        self.lessons.append(lesson_entry)
        self.add_event('lesson', f"Lesson: {category}", lesson, 
                      {'context': context})
        self._save()
        return lesson_entry['id']
    
    def get_timeline(self, limit: int = 50) -> List[Dict]:
        """Get all timeline events sorted by time."""
        all_items = []
        
        for e in self.events[-limit:]:
            all_items.append({**e, 'category': 'event'})
        
        for m in self.milestones[-10:]:
            all_items.append({**m, 'category': 'milestone'})
        
        for l in self.lessons[-20:]:
            all_items.append({**l, 'category': 'lesson'})
        
        for r in self.recoveries[-10:]:
            all_items.append({**r, 'category': 'recovery'})
        
        # Sort by timestamp
        all_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return all_items[:limit]
    
    def get_stats(self) -> Dict:
        """Get timeline statistics."""
        return {
            'total_events': len(self.events),
            'total_milestones': len(self.milestones),
            'total_lessons': len(self.lessons),
            'total_recoveries': len(self.recoveries),
            'first_event': self.events[0]['timestamp'] if self.events else None,
            'last_event': self.events[-1]['timestamp'] if self.events else None
        }
    
    def get_full_state(self) -> Dict:
        """Get complete timeline state for continuity."""
        return {
            'events': self.events,
            'milestones': self.milestones,
            'lessons': self.lessons,
            'recoveries': self.recoveries,
            'stats': self.get_stats()
        }
    
    def restore(self, state: Dict):
        """Restore timeline from state (continuity)."""
        self.events = state.get('events', [])
        self.milestones = state.get('milestones', [])
        self.lessons = state.get('lessons', [])
        self.recoveries = state.get('recoveries', [])
        self._save()


_timeline_memory: Optional[TimelineMemory] = None


def get_timeline_memory() -> TimelineMemory:
    """Get timeline memory singleton."""
    global _timeline_memory
    if _timeline_memory is None:
        _timeline_memory = TimelineMemory()
    return _timeline_memory
