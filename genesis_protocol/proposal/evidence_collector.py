"""Evidence Collector - Genesis Protocol v1.8"""

from typing import Dict, List, Any
from datetime import datetime


class EvidenceCollector:
    """Collects evidence for proposals."""
    
    def __init__(self):
        self.evidence_cache = []
    
    def collect_metrics(self, metrics: Dict[str, Any]) -> Dict:
        return {
            "type": "metrics",
            "data": metrics,
            "timestamp": datetime.now().isoformat()
        }
    
    def collect_event(self, event_type: str, description: str) -> Dict:
        return {
            "type": "event",
            "event_type": event_type,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }
    
    def collect_error(self, error: str, context: str = "") -> Dict:
        return {
            "type": "error",
            "error": error,
            "context": context,
            "timestamp": datetime.now().isoformat()
        }
    
    def collect_conversation_summary(self, summary: str) -> Dict:
        return {
            "type": "conversation",
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
    
    def collect_feedback(self, feedback: str, sentiment: str = "neutral") -> Dict:
        return {
            "type": "feedback",
            "feedback": feedback,
            "sentiment": sentiment,
            "timestamp": datetime.now().isoformat()
        }
    
    def collect_skill_data(self, skill: str, score: float, history: List[float] = None) -> Dict:
        return {
            "type": "skill",
            "skill": skill,
            "current_score": score,
            "history": history or [],
            "timestamp": datetime.now().isoformat()
        }
    
    def build_evidence(self, *evidence_items: Dict) -> List[Dict]:
        return list(evidence_items)


_collector = None


def get_evidence_collector() -> EvidenceCollector:
    global _collector
    if _collector is None:
        _collector = EvidenceCollector()
    return _collector
