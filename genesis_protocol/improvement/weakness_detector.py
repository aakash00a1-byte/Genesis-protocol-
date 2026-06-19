"""Weakness Detector - Genesis Protocol v1.7
Tracks weaknesses over time."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
from pathlib import Path


class WeaknessType(Enum):
    """Types of weaknesses."""
    MEMORY_RECALL = "memory_recall"
    CODING_ACCURACY = "coding_accuracy"
    RESPONSE_LATENCY = "response_latency"
    TASK_COMPLETION = "task_completion"
    PROVIDER_FAILURE = "provider_failure"
    TOOL_FAILURE = "tool_failure"
    QUALITY_ISSUE = "quality_issue"
    OTHER = "other"


@dataclass
class Weakness:
    """A detected weakness."""
    id: str
    weakness_type: WeaknessType
    severity: float  # 0.0 - 1.0
    description: str
    evidence: List[str]
    first_detected: datetime
    last_detected: datetime
    occurrences: int
    status: str = "active"  # active, improving, resolved


class WeaknessDetector:
    """Detects and tracks weaknesses over time."""
    
    def __init__(self, storage_path: str = "./data/weaknesses"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._weaknesses: Dict[str, Weakness] = {}
        self._load_weaknesses()
    
    def _load_weaknesses(self):
        """Load weaknesses from disk."""
        weak_file = self.storage_path / "weaknesses.json"
        if weak_file.exists():
            try:
                with open(weak_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    item['weakness_type'] = WeaknessType(item['weakness_type'])
                    item['first_detected'] = datetime.fromisoformat(item['first_detected'])
                    item['last_detected'] = datetime.fromisoformat(item['last_detected'])
                    self._weaknesses[item['id']] = Weakness(**item)
            except Exception:
                pass
    
    def _save_weaknesses(self):
        """Save weaknesses to disk."""
        weak_file = self.storage_path / "weaknesses.json"
        data = [w.__dict__ for w in self._weaknesses.values()]
        for d in data:
            d['weakness_type'] = d['weakness_type'].value
            d['first_detected'] = d['first_detected'].isoformat()
            d['last_detected'] = d['last_detected'].isoformat()
        try:
            with open(weak_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def detect_weakness(
        self,
        weakness_type: WeaknessType,
        description: str,
        evidence: List[str],
        severity: float
    ) -> Weakness:
        """Detect or update a weakness."""
        # Generate ID from type
        weak_id = weakness_type.value
        
        if weak_id in self._weaknesses:
            # Update existing weakness
            weak = self._weaknesses[weak_id]
            weak.occurrences += 1
            weak.last_detected = datetime.now()
            weak.evidence.extend(evidence[:5])  # Keep last 5 pieces of evidence
            weak.evidence = weak.evidence[-10:]  # Max 10
            weak.severity = max(weak.severity, severity)
            weak.description = description
        else:
            # New weakness
            weak = Weakness(
                id=weak_id,
                weakness_type=weakness_type,
                severity=severity,
                description=description,
                evidence=evidence[:5],
                first_detected=datetime.now(),
                last_detected=datetime.now(),
                occurrences=1
            )
            self._weaknesses[weak_id] = weak
        
        self._save_weaknesses()
        return weak
    
    def check_from_stats(self, skill_stats: Dict[str, Any], evaluation_stats: Dict[str, Any]):
        """Check for weaknesses from statistics."""
        # Check skill weaknesses
        for skill, score in skill_stats.get("scores_24h", {}).items():
            if score < 0.5:
                self.detect_weakness(
                    weakness_type=self._get_weakness_type(skill),
                    description=f"Low {skill} score: {score:.1%}",
                    evidence=[f"Score: {score:.1%}"],
                    severity=1.0 - score
                )
        
        # Check evaluation weaknesses
        if evaluation_stats.get("success_rate", 1.0) < 0.8:
            self.detect_weakness(
                weakness_type=WeaknessType.QUALITY_ISSUE,
                description=f"Low success rate: {evaluation_stats.get('success_rate', 0):.1%}",
                evidence=["Low success rate detected"],
                severity=1.0 - evaluation_stats.get("success_rate", 0)
            )
    
    def _get_weakness_type(self, skill: str) -> WeaknessType:
        """Map skill to weakness type."""
        mapping = {
            "memory_recall": WeaknessType.MEMORY_RECALL,
            "coding_accuracy": WeaknessType.CODING_ACCURACY,
            "task_completion": WeaknessType.TASK_COMPLETION,
            "response_speed": WeaknessType.RESPONSE_LATENCY,
        }
        return mapping.get(skill, WeaknessType.OTHER)
    
    def get_active_weaknesses(self) -> List[Weakness]:
        """Get all active weaknesses sorted by severity."""
        active = [w for w in self._weaknesses.values() if w.status == "active"]
        return sorted(active, key=lambda w: w.severity, reverse=True)
    
    def get_top_weaknesses(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top weaknesses as dict."""
        top = self.get_active_weaknesses()[:limit]
        return [
            {
                "type": w.weakness_type.value if hasattr(w.weakness_type, "value") else str(w.weakness_type),
                "severity": w.severity,
                "description": w.description,
                "occurrences": w.occurrences
            }
            for w in top
        ]
    
    def mark_resolved(self, weakness_id: str):
        """Mark a weakness as resolved."""
        if weakness_id in self._weaknesses:
            self._weaknesses[weakness_id].status = "resolved"
            self._save_weaknesses()
    
    def get_summary(self) -> Dict[str, Any]:
        """Get weakness summary."""
        active = self.get_active_weaknesses()
        return {
            "total_weaknesses": len(self._weaknesses),
            "active_count": len(active),
            "top_weaknesses": self.get_top_weaknesses(3),
            "average_severity": sum(w.severity for w in active) / max(1, len(active))
        }


# Global singleton
_weakness_detector: Optional[WeaknessDetector] = None


def get_weakness_detector() -> WeaknessDetector:
    """Get global weakness detector."""
    global _weakness_detector
    if _weakness_detector is None:
        _weakness_detector = WeaknessDetector()
    return _weakness_detector
