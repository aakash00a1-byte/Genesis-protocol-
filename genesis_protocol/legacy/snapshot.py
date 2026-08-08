"""Snapshot Layer - GLUTTONY Legacy

Periodic snapshots: daily, weekly, monthly.
Allows rollback and recovery."""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path


class SnapshotLayer:
    """Periodic snapshots for recovery and rollback."""
    
    SNAPSHOT_TYPES = ['daily', 'weekly', 'monthly']
    
    def __init__(self, storage_path: str = "data/legacy/snapshots"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.snapshots: List[Dict] = []
        self._load_snapshots_list()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        for snap_type in self.SNAPSHOT_TYPES:
            Path(self.storage_path, snap_type).mkdir(parents=True, exist_ok=True)
    
    def _load_snapshots_list(self):
        """Load snapshots list from disk."""
        list_path = os.path.join(self.storage_path, "snapshots.json")
        if os.path.exists(list_path):
            try:
                with open(list_path, 'r') as f:
                    self.snapshots = json.load(f)
            except Exception:
                self.snapshots = []
        else:
            self.snapshots = []
    
    def _save_snapshots_list(self):
        """Save snapshots list to disk."""
        list_path = os.path.join(self.storage_path, "snapshots.json")
        with open(list_path, 'w') as f:
            json.dump(self.snapshots, f, indent=2)
    
    def create_snapshot(self, state: Dict, snapshot_type: str = 'daily',
                       label: str = "") -> str:
        """Create a snapshot of current state."""
        if snapshot_type not in self.SNAPSHOT_TYPES:
            snapshot_type = 'daily'
        
        timestamp = datetime.now()
        snapshot_id = f"{snapshot_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}"
        
        snapshot_data = {
            'id': snapshot_id,
            'type': snapshot_type,
            'label': label,
            'created_at': timestamp.isoformat(),
            'state': state,
            'metadata': {
                'size_bytes': len(json.dumps(state)),
                'keys': list(state.keys()) if isinstance(state, dict) else []
            }
        }
        
        # Save snapshot file
        filepath = os.path.join(self.storage_path, snapshot_type, f"{snapshot_id}.json")
        with open(filepath, 'w') as f:
            json.dump(snapshot_data, f, indent=2)
        
        # Update snapshots list
        self.snapshots.append({
            'id': snapshot_id,
            'type': snapshot_type,
            'label': label,
            'created_at': timestamp.isoformat(),
            'filepath': filepath
        })
        self._save_snapshots_list()
        
        return snapshot_id
    
    def get_snapshots(self, snapshot_type: str = None) -> List[Dict]:
        """Get list of snapshots."""
        if snapshot_type:
            return [s for s in self.snapshots if s.get('type') == snapshot_type]
        return self.snapshots
    
    def get_latest_snapshot(self, snapshot_type: str = None) -> Optional[Dict]:
        """Get the latest snapshot."""
        filtered = self.get_snapshots(snapshot_type)
        if filtered:
            return filtered[-1]
        return None
    
    def load_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """Load a specific snapshot."""
        for snap in self.snapshots:
            if snap['id'] == snapshot_id:
                filepath = snap.get('filepath')
                if filepath and os.path.exists(filepath):
                    try:
                        with open(filepath, 'r') as f:
                            data = json.load(f)
                        return data.get('state')
                    except Exception:
                        return None
        return None
    
    def restore_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """Restore state from a snapshot."""
        return self.load_snapshot(snapshot_id)
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        for i, snap in enumerate(self.snapshots):
            if snap['id'] == snapshot_id:
                filepath = snap.get('filepath')
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                self.snapshots.pop(i)
                self._save_snapshots_list()
                return True
        return False
    
    def prune_old_snapshots(self, snapshot_type: str, keep_count: int = 10) -> int:
        """Prune old snapshots, keeping only the most recent."""
        filtered = [s for s in self.snapshots if s.get('type') == snapshot_type]
        if len(filtered) <= keep_count:
            return 0
        
        to_remove = filtered[:-keep_count]
        removed = 0
        for snap in to_remove:
            if self.delete_snapshot(snap['id']):
                removed += 1
        
        return removed
    
    def get_stats(self) -> Dict:
        """Get snapshot statistics."""
        stats = {
            'total': len(self.snapshots),
            'by_type': {},
            'total_size_bytes': 0
        }
        
        for snap_type in self.SNAPSHOT_TYPES:
            type_snaps = [s for s in self.snapshots if s.get('type') == snap_type]
            stats['by_type'][snap_type] = len(type_snaps)
            
            # Calculate size
            type_path = os.path.join(self.storage_path, snap_type)
            if os.path.exists(type_path):
                size = sum(os.path.getsize(os.path.join(type_path, f)) 
                          for f in os.listdir(type_path) 
                          if f.endswith('.json'))
                stats['total_size_bytes'] += size
        
        return stats


_snapshot_layer: Optional[SnapshotLayer] = None


def get_snapshot_layer() -> SnapshotLayer:
    """Get snapshot layer singleton."""
    global _snapshot_layer
    if _snapshot_layer is None:
        _snapshot_layer = SnapshotLayer()
    return _snapshot_layer
