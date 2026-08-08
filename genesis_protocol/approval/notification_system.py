"""Notification System - Genesis Protocol v1.9"""

from typing import Dict, List


class NotificationSystem:
    def __init__(self):
        self._notifications: List[Dict] = []
    
    def notify_approved(self, proposal_id: str):
        self._notifications.append({"event": "approved", "proposal_id": proposal_id})
    
    def notify_rejected(self, proposal_id: str, reason: str = ""):
        self._notifications.append({"event": "rejected", "proposal_id": proposal_id, "reason": reason})
    
    def get_notifications(self) -> List[Dict]:
        return self._notifications[-50:]


_ns = None


def get_notification_system() -> NotificationSystem:
    global _ns
    if _ns is None:
        _ns = NotificationSystem()
    return _ns
