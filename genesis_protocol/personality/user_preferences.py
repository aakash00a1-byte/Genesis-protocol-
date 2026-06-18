"""User Preferences - Genesis Protocol v1.1"""

import json
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


@dataclass
class UserPreference:
    """Individual user preference."""
    key: str
    value: Any
    category: str = "general"
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class UserPreferences:
    """User preferences and memory."""
    user_id: int
    name: Optional[str] = None
    language: str = "en"
    timezone: str = "UTC"
    interests: List[str] = field(default_factory=list)
    preferences: Dict[str, Any] = field(default_factory=dict)
    interaction_history: int = 0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    
    def update_preference(self, key: str, value: Any, category: str = "general"):
        """Update a preference."""
        self.preferences[key] = UserPreference(
            key=key, value=value, category=category
        )
        self.last_seen = datetime.now()
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a preference value."""
        pref = self.preferences.get(key)
        return pref.value if pref else default
    
    def add_interest(self, interest: str):
        """Add an interest."""
        if interest.lower() not in [i.lower() for i in self.interests]:
            self.interests.append(interest)
    
    def remove_interest(self, interest: str):
        """Remove an interest."""
        self.interests = [i for i in self.interests if i.lower() != interest.lower()]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        data = asdict(self)
        data['preferences'] = {k: asdict(v) for k, v in self.preferences.items()}
        data['first_seen'] = self.first_seen.isoformat()
        data['last_seen'] = self.last_seen.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, user_id: int, data: Dict[str, Any]) -> 'UserPreferences':
        """Deserialize from dict."""
        prefs = cls(user_id=user_id)
        for key, value in data.items():
            if key == 'preferences':
                prefs.preferences = {
                    k: UserPreference(**v) for k, v in value.items()
                }
            elif key == 'first_seen':
                prefs.first_seen = datetime.fromisoformat(value)
            elif key == 'last_seen':
                prefs.last_seen = datetime.fromisoformat(value)
            elif hasattr(prefs, key):
                setattr(prefs, key, value)
        return prefs


class PreferenceManager:
    """Manages user preferences persistence."""
    
    def __init__(self, storage_path: str = "./data/preferences"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[int, UserPreferences] = {}
    
    def _get_file_path(self, user_id: int) -> Path:
        """Get file path for user."""
        return self.storage_path / f"user_{user_id}.json"
    
    def load(self, user_id: int) -> UserPreferences:
        """Load user preferences."""
        if user_id in self._cache:
            return self._cache[user_id]
        
        file_path = self._get_file_path(user_id)
        if file_path.exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
            prefs = UserPreferences.from_dict(user_id, data)
        else:
            prefs = UserPreferences(user_id=user_id)
        
        self._cache[user_id] = prefs
        return prefs
    
    def save(self, prefs: UserPreferences):
        """Save user preferences."""
        self._cache[prefs.user_id] = prefs
        file_path = self._get_file_path(prefs.user_id)
        with open(file_path, 'w') as f:
            json.dump(prefs.to_dict(), f, indent=2)
    
    def delete(self, user_id: int):
        """Delete user preferences."""
        if user_id in self._cache:
            del self._cache[user_id]
        file_path = self._get_file_path(user_id)
        if file_path.exists():
            file_path.unlink()
    
    def get_all_users(self) -> List[int]:
        """Get all user IDs with saved preferences."""
        return [
            int(f.stem.split('_')[1]) 
            for f in self.storage_path.glob("user_*.json")
        ]
