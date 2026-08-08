"""Cross-Device Continuity - GLUTTONY Legacy

Preserves state between local, cloud, and backups."""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
import hashlib


class CrossDeviceContinuity:
    """Manages state preservation across devices and backups."""
    
    def __init__(self, base_path: str = "data/legacy/cross_device"):
        self.base_path = base_path
        self._ensure_storage()
        
        # Local storage
        self.local_path = os.path.join(base_path, "local")
        # Cloud sync path
        self.cloud_path = os.path.join(base_path, "cloud")
        # Backup storage
        self.backup_path = os.path.join(base_path, "backups")
        
        # Sync metadata
        self.sync_log: List[Dict] = []
        self._load_sync_log()
    
    def _ensure_storage(self):
        """Ensure storage directories exist."""
        Path(self.base_path).mkdir(parents=True, exist_ok=True)
        Path(self.local_path).mkdir(parents=True, exist_ok=True)
        Path(self.cloud_path).mkdir(parents=True, exist_ok=True)
        Path(self.backup_path).mkdir(parents=True, exist_ok=True)
    
    def _load_sync_log(self):
        """Load sync log."""
        log_path = os.path.join(self.base_path, "sync_log.json")
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r') as f:
                    self.sync_log = json.load(f)
            except Exception:
                self.sync_log = []
    
    def _save_sync_log(self):
        """Save sync log."""
        log_path = os.path.join(self.base_path, "sync_log.json")
        with open(log_path, 'w') as f:
            json.dump(self.sync_log, f, indent=2)
    
    def _get_checksum(self, data: Any) -> str:
        """Get checksum of data."""
        return hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
    
    def save_local(self, key: str, data: Dict) -> str:
        """Save data to local storage."""
        filepath = os.path.join(self.local_path, f"{key}.json")
        
        wrapped = {
            'key': key,
            'data': data,
            'checksum': self._get_checksum(data),
            'saved_at': datetime.now().isoformat(),
            'location': 'local'
        }
        
        with open(filepath, 'w') as f:
            json.dump(wrapped, f, indent=2)
        
        # Update sync log
        self.sync_log.append({
            'action': 'save_local',
            'key': key,
            'timestamp': datetime.now().isoformat(),
            'checksum': wrapped['checksum']
        })
        self._save_sync_log()
        
        return filepath
    
    def load_local(self, key: str) -> Optional[Dict]:
        """Load data from local storage."""
        filepath = os.path.join(self.local_path, f"{key}.json")
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r') as f:
                wrapped = json.load(f)
            return wrapped.get('data')
        except Exception:
            return None
    
    def save_to_cloud(self, key: str, data: Dict) -> str:
        """Simulate saving to cloud storage."""
        filepath = os.path.join(self.cloud_path, f"{key}.json")
        
        wrapped = {
            'key': key,
            'data': data,
            'checksum': self._get_checksum(data),
            'saved_at': datetime.now().isoformat(),
            'synced_at': datetime.now().isoformat(),
            'location': 'cloud'
        }
        
        with open(filepath, 'w') as f:
            json.dump(wrapped, f, indent=2)
        
        self.sync_log.append({
            'action': 'save_cloud',
            'key': key,
            'timestamp': datetime.now().isoformat(),
            'checksum': wrapped['checksum']
        })
        self._save_sync_log()
        
        return filepath
    
    def load_from_cloud(self, key: str) -> Optional[Dict]:
        """Load data from cloud storage."""
        filepath = os.path.join(self.cloud_path, f"{key}.json")
        
        if not os.path.exists(filepath):
            return None
        
        try:
            with open(filepath, 'r') as f:
                wrapped = json.load(f)
            return wrapped.get('data')
        except Exception:
            return None
    
    def create_backup(self, key: str, data: Dict) -> str:
        """Create a backup."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{key}_{timestamp}.json"
        filepath = os.path.join(self.backup_path, filename)
        
        wrapped = {
            'key': key,
            'data': data,
            'checksum': self._get_checksum(data),
            'backed_up_at': datetime.now().isoformat(),
            'backup_id': f"backup_{timestamp}"
        }
        
        with open(filepath, 'w') as f:
            json.dump(wrapped, f, indent=2)
        
        self.sync_log.append({
            'action': 'backup',
            'key': key,
            'timestamp': datetime.now().isoformat(),
            'backup_id': wrapped['backup_id']
        })
        self._save_sync_log()
        
        return filepath
    
    def list_backups(self, key: str = None) -> List[Dict]:
        """List available backups."""
        backups = []
        
        for filename in os.listdir(self.backup_path):
            if filename.endswith('.json'):
                # Parse key and timestamp from filename
                parts = filename.replace('.json', '').split('_')
                if len(parts) >= 2:
                    backup_key = parts[0]
                    if key is None or backup_key == key:
                        filepath = os.path.join(self.backup_path, filename)
                        try:
                            with open(filepath, 'r') as f:
                                wrapped = json.load(f)
                            backups.append({
                                'backup_id': wrapped.get('backup_id'),
                                'key': wrapped.get('key'),
                                'backed_up_at': wrapped.get('backed_up_at'),
                                'filepath': filepath
                            })
                        except Exception:
                            pass
        
        return sorted(backups, key=lambda x: x.get('backed_up_at', ''), reverse=True)
    
    def restore_from_backup(self, backup_id: str) -> Optional[Dict]:
        """Restore data from a specific backup."""
        for filename in os.listdir(self.backup_path):
            if filename.endswith('.json'):
                filepath = os.path.join(self.backup_path, filename)
                try:
                    with open(filepath, 'r') as f:
                        wrapped = json.load(f)
                    if wrapped.get('backup_id') == backup_id:
                        return wrapped.get('data')
                except Exception:
                    pass
        return None
    
    def sync_to_cloud(self, key: str) -> bool:
        """Sync local data to cloud."""
        local_data = self.load_local(key)
        if local_data is None:
            return False
        
        self.save_to_cloud(key, local_data)
        
        self.sync_log.append({
            'action': 'sync',
            'direction': 'local_to_cloud',
            'key': key,
            'timestamp': datetime.now().isoformat()
        })
        self._save_sync_log()
        
        return True
    
    def restore_from_cloud(self, key: str) -> bool:
        """Restore local data from cloud."""
        cloud_data = self.load_from_cloud(key)
        if cloud_data is None:
            return False
        
        self.save_local(key, cloud_data)
        
        self.sync_log.append({
            'action': 'restore',
            'direction': 'cloud_to_local',
            'key': key,
            'timestamp': datetime.now().isoformat()
        })
        self._save_sync_log()
        
        return True
    
    def get_storage_info(self) -> Dict:
        """Get storage information."""
        info = {
            'local': {
                'path': self.local_path,
                'files': len(os.listdir(self.local_path)) if os.path.exists(self.local_path) else 0
            },
            'cloud': {
                'path': self.cloud_path,
                'files': len(os.listdir(self.cloud_path)) if os.path.exists(self.cloud_path) else 0
            },
            'backups': {
                'path': self.backup_path,
                'count': len(os.listdir(self.backup_path)) if os.path.exists(self.backup_path) else 0
            },
            'sync_log_entries': len(self.sync_log)
        }
        
        return info


_cross_device: Optional[CrossDeviceContinuity] = None


def get_cross_device_continuity() -> CrossDeviceContinuity:
    """Get cross-device continuity singleton."""
    global _cross_device
    if _cross_device is None:
        _cross_device = CrossDeviceContinuity()
    return _cross_device
