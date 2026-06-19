"""Relationship History - GLUTTONY Legacy

Tracks first meetings, major events, shared projects, and recoveries."""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class RelationshipHistory:
    """Persistent relationship history tracking."""
    
    def __init__(self, storage_path: str = "data/legacy/relationship_history.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        
        # Relationships: entity_id -> {first_meeting, events, shared_projects, recoveries}
        self.relationships: Dict[str, Dict] = {}
        
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load relationship history from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self.relationships = json.load(f)
            except:
                pass
    
    def _save(self):
        """Save relationship history to disk."""
        with open(self.storage_path, 'w') as f:
            json.dump(self.relationships, f, indent=2)
    
    def get_or_create_relationship(self, entity_id: str, entity_name: str = "") -> Dict:
        """Get or create a relationship entry."""
        if entity_id not in self.relationships:
            self.relationships[entity_id] = {
                'entity_id': entity_id,
                'entity_name': entity_name or entity_id,
                'first_meeting': datetime.now().isoformat(),
                'last_interaction': datetime.now().isoformat(),
                'major_events': [],
                'shared_projects': [],
                'recoveries': [],
                'interaction_count': 0
            }
            self._save()
        
        return self.relationships[entity_id]
    
    def record_interaction(self, entity_id: str, entity_name: str = "",
                          interaction_type: str = "conversation",
                          summary: str = "") -> str:
        """Record an interaction."""
        rel = self.get_or_create_relationship(entity_id, entity_name)
        rel['last_interaction'] = datetime.now().isoformat()
        rel['interaction_count'] += 1
        
        event = {
            'id': f"evt_{len(rel['major_events'])}_{int(datetime.now().timestamp())}",
            'type': interaction_type,
            'summary': summary,
            'timestamp': datetime.now().isoformat()
        }
        rel['major_events'].append(event)
        
        self._save()
        return event['id']
    
    def add_shared_project(self, entity_id: str, project_name: str,
                          status: str = "active",
                          description: str = "") -> str:
        """Add a shared project."""
        rel = self.get_or_create_relationship(entity_id)
        
        project = {
            'id': f"proj_{len(rel['shared_projects'])}_{int(datetime.now().timestamp())}",
            'name': project_name,
            'status': status,
            'description': description,
            'started_at': datetime.now().isoformat(),
            'ended_at': None
        }
        
        rel['shared_projects'].append(project)
        self._save()
        return project['id']
    
    def complete_project(self, entity_id: str, project_id: str) -> bool:
        """Mark a project as completed."""
        if entity_id not in self.relationships:
            return False
        
        for proj in self.relationships[entity_id]['shared_projects']:
            if proj['id'] == project_id:
                proj['status'] = 'completed'
                proj['ended_at'] = datetime.now().isoformat()
                self._save()
                return True
        
        return False
    
    def add_recovery(self, entity_id: str, failure: str,
                    recovery_method: str, lessons: str = "") -> str:
        """Record a recovery with this entity."""
        rel = self.get_or_create_relationship(entity_id)
        
        recovery = {
            'id': f"rec_{len(rel['recoveries'])}_{int(datetime.now().timestamp())}",
            'failure': failure,
            'recovery_method': recovery_method,
            'lessons': lessons,
            'recovered_at': datetime.now().isoformat()
        }
        
        rel['recoveries'].append(recovery)
        self._save()
        return recovery['id']
    
    def add_major_event(self, entity_id: str, event_type: str,
                       description: str, significance: str = "medium") -> str:
        """Add a major event."""
        rel = self.get_or_create_relationship(entity_id)
        
        event = {
            'id': f"major_{len(rel['major_events'])}_{int(datetime.now().timestamp())}",
            'type': event_type,
            'description': description,
            'significance': significance,
            'timestamp': datetime.now().isoformat()
        }
        
        rel['major_events'].append(event)
        self._save()
        return event['id']
    
    def get_relationship(self, entity_id: str) -> Optional[Dict]:
        """Get relationship details."""
        return self.relationships.get(entity_id)
    
    def get_all_relationships(self) -> List[Dict]:
        """Get all relationships."""
        return list(self.relationships.values())
    
    def get_recent_interactions(self, entity_id: str, limit: int = 10) -> List[Dict]:
        """Get recent interactions with an entity."""
        if entity_id not in self.relationships:
            return []
        
        events = self.relationships[entity_id]['major_events']
        return sorted(events, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
    
    def get_stats(self) -> Dict:
        """Get relationship history statistics."""
        return {
            'total_relationships': len(self.relationships),
            'total_interactions': sum(r['interaction_count'] for r in self.relationships.values()),
            'total_projects': sum(len(r['shared_projects']) for r in self.relationships.values()),
            'total_recoveries': sum(len(r['recoveries']) for r in self.relationships.values())
        }


_relationship_history: Optional[RelationshipHistory] = None


def get_relationship_history() -> RelationshipHistory:
    """Get relationship history singleton."""
    global _relationship_history
    if _relationship_history is None:
        _relationship_history = RelationshipHistory()
    return _relationship_history
