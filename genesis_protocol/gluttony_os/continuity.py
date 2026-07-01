"""Continuity Layer - GLUTTONY Presence Layer

Restores identity, timeline, state, trust, and journal after restart."""

import json
import os
import threading
from datetime import datetime
from typing import Dict, Optional
from pathlib import Path


class ContinuityLayer:
    """Manages state persistence and restoration across restarts."""
    
    def __init__(self, storage_path: str = "data/continuity.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.state_version = "1.0"
        self._lock = threading.Lock()
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load continuity state from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self.state = json.load(f)
            except:
                self._init_empty()
        else:
            self._init_empty()
    
    def _init_empty(self):
        """Initialize empty continuity state."""
        self.state = {
            'version': self.state_version,
            'created_at': datetime.now().isoformat(),
            'last_updated': datetime.now().isoformat(),
            'identity': None,
            'timeline': None,
            'trust': None,
            'journal': None,
            'relationship': None,
            'wisdom': None,
            'gluttony_state': None,
            'uptime_simulation': {
                'simulated_days': 0,
                'restarts': 0
            }
        }
    
    def _save(self):
        """Save continuity state to disk."""
        with self._lock:
            self.state['last_updated'] = datetime.now().isoformat()
            with open(self.storage_path, 'w') as f:
                json.dump(self.state, f, indent=2)
    
    def save_identity(self, identity_data: Dict):
        """Save identity state."""
        self.state['identity'] = identity_data
        self._save()
    
    def save_timeline(self, timeline_state: Dict):
        """Save timeline state."""
        self.state['timeline'] = timeline_state
        self._save()
    
    def save_trust(self, trust_state: Dict):
        """Save trust model state."""
        self.state['trust'] = trust_state
        self._save()
    
    def save_journal(self, journal_state: Dict):
        """Save journal state."""
        self.state['journal'] = journal_state
        self._save()
    
    def save_relationship(self, relationship_state: Dict):
        """Save relationship memory state."""
        self.state['relationship'] = relationship_state
        self._save()
    
    def save_wisdom(self, wisdom_state: Dict):
        """Save wisdom layer state."""
        self.state['wisdom'] = wisdom_state
        self._save()
    
    def save_gluttony_state(self, state: Dict):
        """Save GLUTTONY core state."""
        self.state['gluttony_state'] = state
        self._save()
    
    def save_full_state(self, all_states: Dict):
        """Save complete system state."""
        with self._lock:
            self.state['identity'] = all_states.get('identity')
            self.state['timeline'] = all_states.get('timeline')
            self.state['trust'] = all_states.get('trust')
            self.state['journal'] = all_states.get('journal')
            self.state['relationship'] = all_states.get('relationship')
            self.state['wisdom'] = all_states.get('wisdom')
            self.state['gluttony_state'] = all_states.get('gluttony_state')
            self._save()
    
    def restore_identity(self) -> Optional[Dict]:
        """Restore identity state."""
        return self.state.get('identity')
    
    def restore_timeline(self) -> Optional[Dict]:
        """Restore timeline state."""
        return self.state.get('timeline')
    
    def restore_trust(self) -> Optional[Dict]:
        """Restore trust model state."""
        return self.state.get('trust')
    
    def restore_journal(self) -> Optional[Dict]:
        """Restore journal state."""
        return self.state.get('journal')
    
    def restore_relationship(self) -> Optional[Dict]:
        """Restore relationship memory state."""
        return self.state.get('relationship')
    
    def restore_wisdom(self) -> Optional[Dict]:
        """Restore wisdom layer state."""
        return self.state.get('wisdom')
    
    def restore_gluttony_state(self) -> Optional[Dict]:
        """Restore GLUTTONY core state."""
        return self.state.get('gluttony_state')
    
    def restore_all(self) -> Dict:
        """Restore all states at once."""
        return {
            'identity': self.state.get('identity'),
            'timeline': self.state.get('timeline'),
            'trust': self.state.get('trust'),
            'journal': self.state.get('journal'),
            'relationship': self.state.get('relationship'),
            'wisdom': self.state.get('wisdom'),
            'gluttony_state': self.state.get('gluttony_state')
        }
    
    def get_continuity_status(self) -> Dict:
        """Get continuity status."""
        return {
            'version': self.state.get('version'),
            'created_at': self.state.get('created_at'),
            'last_updated': self.state.get('last_updated'),
            'has_identity': self.state.get('identity') is not None,
            'has_timeline': self.state.get('timeline') is not None,
            'has_trust': self.state.get('trust') is not None,
            'has_journal': self.state.get('journal') is not None,
            'has_relationship': self.state.get('relationship') is not None,
            'has_wisdom': self.state.get('wisdom') is not None,
            'has_gluttony_state': self.state.get('gluttony_state') is not None,
            'uptime_simulation': self.state.get('uptime_simulation', {})
        }
    
    def simulate_uptime(self, days: int) -> Dict:
        """Simulate uptime for testing."""
        sim = self.state.get('uptime_simulation', {})
        sim['simulated_days'] = days
        sim['last_simulated'] = datetime.now().isoformat()
        self.state['uptime_simulation'] = sim
        self._save()
        
        return {
            'simulated_days': days,
            'expected_memory_growth': days * 10,  # Rough estimate
            'expected_recoveries': max(0, days - 7) if days > 7 else 0
        }
    
    def record_restart(self):
        """Record a restart for uptime tracking."""
        sim = self.state.get('uptime_simulation', {})
        sim['restarts'] = sim.get('restarts', 0) + 1
        sim['last_restart'] = datetime.now().isoformat()
        self.state['uptime_simulation'] = sim
        self._save()
    
    def get_full_state(self) -> Dict:
        """Get complete continuity state."""
        return self.state.copy()
    
    def clear_all(self):
        """Clear all continuity state."""
        self._init_empty()
        self._save()


_continuity_layer: Optional[ContinuityLayer] = None


def get_continuity_layer() -> ContinuityLayer:
    """Get continuity layer singleton."""
    global _continuity_layer
    if _continuity_layer is None:
        _continuity_layer = ContinuityLayer()
    return _continuity_layer
