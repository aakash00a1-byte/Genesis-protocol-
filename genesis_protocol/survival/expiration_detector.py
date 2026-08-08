"""Expiration Detector - GLUTTONY v3.0 Survival Layer"""
from datetime import datetime, timedelta
from typing import Dict, List


class ExpirationDetector:
    def __init__(self):
        self._tracked_items = []
    
    def track(self, item_id: str, item_type: str, expires_at: datetime, meta: Dict = None):
        self._tracked_items.append({"id": item_id, "type": item_type, "expires_at": expires_at, "meta": meta or {}, "tracked_at": datetime.now()})
    
    def check_expiring(self, within_hours: int = 24) -> List[Dict]:
        now = datetime.now()
        deadline = now + timedelta(hours=within_hours)
        return [item for item in self._tracked_items if item["expires_at"] <= deadline]
    
    def check_expired(self) -> List[Dict]:
        now = datetime.now()
        return [item for item in self._tracked_items if item["expires_at"] <= now]
    
    def get_all(self) -> List[Dict]:
        return self._tracked_items


_expiration_detector = None
def get_expiration_detector() -> ExpirationDetector:
    global _expiration_detector
    if _expiration_detector is None:
        _expiration_detector = ExpirationDetector()
    return _expiration_detector
