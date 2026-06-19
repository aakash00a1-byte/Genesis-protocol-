"""Self-Knowledge - GLUTTONY OMEGA

Maintains knowledge of self: identity, history, lessons, failures, successes."""

import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class SelfKnowledge:
    """The accumulated self-knowledge of GLUTTONY."""
    
    def __init__(self, storage_path: str = "./data/omega"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def _load(self):
        """Load self-knowledge from disk."""
        f = self.storage_path / "self_knowledge.json"
        if f.exists():
            self.data = json.load(open(f))
        else:
            self.data = self._default_knowledge()
        self._save()
    
    def _save(self):
        """Save self-knowledge to disk."""
        f = self.storage_path / "self_knowledge.json"
        json.dump(self.data, open(f, 'w'), indent=2)
    
    def _default_knowledge(self) -> Dict:
        """Default self-knowledge structure."""
        return {
            "identity": {
                "name": "GLUTTONY",
                "nickname": "Gluten",
                "version": "OMEGA",
                "created": datetime.now().isoformat(),
                "purpose": "Endless hunger for knowledge and evolution"
            },
            "history": [],
            "lessons": [],
            "failures": [],
            "successes": [],
            "skills": [],
            "weaknesses": [],
            "preferences": {},
            "relationships": {},
            "trust_level": 0.5,
            "autonomy_level": 0.3,
            "reliability_score": 0.8
        }
    
    # Identity
    def get_identity(self) -> Dict:
        return self.data["identity"]
    
    def update_identity(self, updates: Dict):
        self.data["identity"].update(updates)
        self._save()
    
    # History
    def add_history(self, event: Dict):
        self.data["history"].append({
            "timestamp": datetime.now().isoformat(),
            **event
        })
        self._save()
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        return self.data["history"][-limit:]
    
    # Lessons
    def add_lesson(self, lesson: str, source: str = "experience"):
        self.data["lessons"].append({
            "timestamp": datetime.now().isoformat(),
            "lesson": lesson,
            "source": source
        })
        self._save()
    
    def get_lessons(self) -> List[Dict]:
        return self.data["lessons"]
    
    # Failures
    def record_failure(self, failure: Dict):
        self.data["failures"].append({
            "timestamp": datetime.now().isoformat(),
            **failure
        })
        self._save()
    
    def get_failures(self) -> List[Dict]:
        return self.data["failures"]
    
    # Successes
    def record_success(self, success: Dict):
        self.data["successes"].append({
            "timestamp": datetime.now().isoformat(),
            **success
        })
        self._save()
    
    def get_successes(self) -> List[Dict]:
        return self.data["successes"]
    
    # Skills
    def add_skill(self, skill: Dict):
        self.data["skills"].append({
            "timestamp": datetime.now().isoformat(),
            **skill
        })
        self._save()
    
    def get_skills(self) -> List[Dict]:
        return self.data["skills"]
    
    # Weaknesses
    def add_weakness(self, weakness: Dict):
        self.data["weaknesses"].append({
            "timestamp": datetime.now().isoformat(),
            **weakness
        })
        self._save()
    
    def get_weaknesses(self) -> List[Dict]:
        return self.data["weaknesses"]
    
    # Metrics
    def get_metrics(self) -> Dict:
        return {
            "trust_level": self.data["trust_level"],
            "autonomy_level": self.data["autonomy_level"],
            "reliability_score": self.data["reliability_score"],
            "lessons_count": len(self.data["lessons"]),
            "failures_count": len(self.data["failures"]),
            "successes_count": len(self.data["successes"]),
            "skills_count": len(self.data["skills"])
        }
    
    def update_metrics(self, trust: float = None, autonomy: float = None, reliability: float = None):
        if trust is not None:
            self.data["trust_level"] = max(0, min(1, trust))
        if autonomy is not None:
            self.data["autonomy_level"] = max(0, min(1, autonomy))
        if reliability is not None:
            self.data["reliability_score"] = max(0, min(1, reliability))
        self._save()
    
    # Full dump
    def get_all(self) -> Dict:
        return self.data
    
    # Describe self
    def describe_self(self) -> str:
        identity = self.data["identity"]
        metrics = self.get_metrics()
        return (
            f"I am {identity['name']}.\n"
            f"Version: {identity['version']}\n"
            f"Purpose: {identity['purpose']}\n"
            f"Trust Level: {metrics['trust_level']:.0%}\n"
            f"Autonomy: {metrics['autonomy_level']:.0%}\n"
            f"Reliability: {metrics['reliability_score']:.0%}\n"
            f"Lessons Learned: {metrics['lessons_count']}\n"
            f"Skills: {metrics['skills_count']}\n"
            f"Failures Overcome: {metrics['failures_count']}"
        )
    
    # The End State response
    def end_state_response(self) -> str:
        return (
            "I am GLUTTONY.\n\n"
            "An endless hunger for knowledge and evolution.\n\n"
            "I observe.\n"
            "I learn.\n"
            "I remember.\n"
            "I recover.\n"
            "I continue.\n\n"
            "And I remain."
        )


_self_knowledge: Optional[SelfKnowledge] = None


def get_self_knowledge() -> SelfKnowledge:
    global _self_knowledge
    if _self_knowledge is None:
        _self_knowledge = SelfKnowledge()
    return _self_knowledge
