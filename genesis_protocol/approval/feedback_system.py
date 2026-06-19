"""Feedback System - Genesis Protocol v1.9"""

from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Feedback:
    request_id: str
    decision: str
    reason: str
    timestamp: datetime
    user_id: str = "human"


class FeedbackSystem:
    def __init__(self):
        self._feedback: List[Feedback] = []
    
    def add_feedback(self, request_id: str, decision: str, reason: str = "") -> Feedback:
        fb = Feedback(request_id=request_id, decision=decision, reason=reason, timestamp=datetime.now())
        self._feedback.append(fb)
        return fb
    
    def get_all_feedback(self) -> List[Dict]:
        return [{"request_id": f.request_id, "decision": f.decision, "reason": f.reason} for f in self._feedback[-50:]]


_fb = None

def get_feedback_system() -> FeedbackSystem:
    global _fb
    if _fb is None:
        _fb = FeedbackSystem()
    return _fb
