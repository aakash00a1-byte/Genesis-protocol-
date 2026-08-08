"""Archive Layer - GLUTTONY Legacy

Stores conversations, lessons, milestones, journals, and trust history.
Supports export and restore."""

import json
import os
import gzip
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path


class ArchiveLayer:
    """Persistent archive of all GLUTTONY memories."""
    
    def __init__(self, storage_path: str = "data/archive"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.conversations: List[Dict] = []
        self.lessons_archive: List[Dict] = []
        self.milestones_archive: List[Dict] = []
        self.journals_archive: List[Dict] = []
        self.trust_archive: List[Dict] = []
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        Path(self.storage_path, "snapshots").mkdir(parents=True, exist_ok=True)
        Path(self.storage_path, "exports").mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load archive from disk."""
        archives = [
            ("conversations.json", "conversations"),
            ("lessons.json", "lessons_archive"),
            ("milestones.json", "milestones_archive"),
            ("journals.json", "journals_archive"),
            ("trust.json", "trust_archive")
        ]
        
        for filename, attr in archives:
            path = os.path.join(self.storage_path, filename)
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        setattr(self, attr, data)
                except Exception:
                    pass
    
    def _save(self, attr: str, filename: str):
        """Save specific archive to disk."""
        data = getattr(self, attr, [])
        path = os.path.join(self.storage_path, filename)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def archive_conversation(self, messages: List[Dict], metadata: Dict = None) -> str:
        """Archive a conversation."""
        archive_entry = {
            'id': f"conv_{len(self.conversations)}_{int(datetime.now().timestamp())}",
            'messages': messages,
            'metadata': metadata or {},
            'archived_at': datetime.now().isoformat(),
            'message_count': len(messages)
        }
        self.conversations.append(archive_entry)
        self._save("conversations", "conversations.json")
        return archive_entry['id']
    
    def archive_lesson(self, lesson: str, context: str = "",
                      category: str = "general") -> str:
        """Archive an important lesson."""
        entry = {
            'id': f"les_archive_{len(self.lessons_archive)}_{int(datetime.now().timestamp())}",
            'lesson': lesson,
            'context': context,
            'category': category,
            'archived_at': datetime.now().isoformat()
        }
        self.lessons_archive.append(entry)
        self._save("lessons_archive", "lessons.json")
        return entry['id']
    
    def archive_milestone(self, title: str, description: str,
                         category: str = "general") -> str:
        """Archive a milestone."""
        entry = {
            'id': f"ms_archive_{len(self.milestones_archive)}_{int(datetime.now().timestamp())}",
            'title': title,
            'description': description,
            'category': category,
            'archived_at': datetime.now().isoformat()
        }
        self.milestones_archive.append(entry)
        self._save("milestones_archive", "milestones.json")
        return entry['id']
    
    def archive_journal_entry(self, entry_type: str, content: str,
                              tags: List[str] = None) -> str:
        """Archive a journal entry."""
        entry = {
            'id': f"jrn_archive_{len(self.journals_archive)}_{int(datetime.now().timestamp())}",
            'type': entry_type,
            'content': content,
            'tags': tags or [],
            'archived_at': datetime.now().isoformat()
        }
        self.journals_archive.append(entry)
        self._save("journals_archive", "journals.json")
        return entry['id']
    
    def archive_trust_state(self, trust_data: Dict) -> str:
        """Archive trust state."""
        entry = {
            'id': f"trust_archive_{len(self.trust_archive)}_{int(datetime.now().timestamp())}",
            'trust_data': trust_data,
            'archived_at': datetime.now().isoformat()
        }
        self.trust_archive.append(entry)
        self._save("trust_archive", "trust.json")
        return entry['id']
    
    def export_all(self, compressed: bool = False) -> str:
        """Export entire archive."""
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'version': '1.0',
            'conversations': self.conversations,
            'lessons': self.lessons_archive,
            'milestones': self.milestones_archive,
            'journals': self.journals_archive,
            'trust': self.trust_archive,
            'counts': {
                'conversations': len(self.conversations),
                'lessons': len(self.lessons_archive),
                'milestones': len(self.milestones_archive),
                'journals': len(self.journals_archive),
                'trust_entries': len(self.trust_archive)
            }
        }
        
        if compressed:
            filename = f"archive_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json.gz"
            filepath = os.path.join(self.storage_path, "exports", filename)
            with gzip.open(filepath, 'wt') as f:
                json.dump(export_data, f)
        else:
            filename = f"archive_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            filepath = os.path.join(self.storage_path, "exports", filename)
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2)
        
        return filepath
    
    def restore_from_file(self, filepath: str) -> bool:
        """Restore archive from file."""
        try:
            if filepath.endswith('.gz'):
                with gzip.open(filepath, 'rt') as f:
                    data = json.load(f)
            else:
                with open(filepath, 'r') as f:
                    data = json.load(f)
            
            self.conversations = data.get('conversations', [])
            self.lessons_archive = data.get('lessons', [])
            self.milestones_archive = data.get('milestones', [])
            self.journals_archive = data.get('journals', [])
            self.trust_archive = data.get('trust', [])
            
            self._save("conversations", "conversations.json")
            self._save("lessons_archive", "lessons.json")
            self._save("milestones_archive", "milestones.json")
            self._save("journals_archive", "journals.json")
            self._save("trust_archive", "trust.json")
            
            return True
        except Exception:
            return False
    
    def get_stats(self) -> Dict:
        """Get archive statistics."""
        return {
            'total_conversations': len(self.conversations),
            'total_lessons': len(self.lessons_archive),
            'total_milestones': len(self.milestones_archive),
            'total_journals': len(self.journals_archive),
            'total_trust_entries': len(self.trust_archive),
            'storage_path': self.storage_path
        }
    
    def get_all(self) -> Dict:
        """Get all archived data."""
        return {
            'conversations': self.conversations[-50:],
            'lessons': self.lessons_archive[-100:],
            'milestones': self.milestones_archive,
            'journals': self.journals_archive[-100:],
            'trust': self.trust_archive[-50:],
            'stats': self.get_stats()
        }


_archive_layer: Optional[ArchiveLayer] = None


def get_archive_layer() -> ArchiveLayer:
    """Get archive layer singleton."""
    global _archive_layer
    if _archive_layer is None:
        _archive_layer = ArchiveLayer()
    return _archive_layer
