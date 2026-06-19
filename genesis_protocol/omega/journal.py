"""Journal - GLUTTONY OMEGA

Continuous reflection and learning through journaling."""

import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class Journal:
    """GLUTTONY's daily journal for reflection and learning."""
    
    def __init__(self, storage_path: str = "./data/omega/journal"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._entries = []
        self._load_today()
    
    def _load_today(self):
        """Load today's journal entries."""
        today = datetime.now().strftime("%Y-%m-%d")
        f = self.storage_path / f"{today}.json"
        if f.exists():
            self._entries = json.load(open(f))
        else:
            self._entries = []
    
    def _save(self):
        """Save journal entries."""
        today = datetime.now().strftime("%Y-%m-%d")
        f = self.storage_path / f"{today}.json"
        json.dump(self._entries, open(f, 'w'), indent=2)
    
    def write(self, entry_type: str, content: str, tags: List[str] = None):
        """Write a journal entry."""
        self._entries.append({
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content,
            "tags": tags or []
        })
        self._save()
    
    def observe(self, observation: str):
        """Record an observation."""
        self.write("observation", observation, ["observe"])
    
    def reflect(self, reflection: str):
        """Record a reflection."""
        self.write("reflection", reflection, ["reflect"])
    
    def learn(self, lesson: str):
        """Record a learned lesson."""
        self.write("lesson", lesson, ["learn"])
    
    def predict(self, prediction: str, outcome: str = None):
        """Record a prediction."""
        entry = {"prediction": prediction}
        if outcome:
            entry["outcome"] = outcome
            entry["correct"] = prediction.lower() in outcome.lower()
        self.write("prediction", str(entry), ["predict"])
    
    def experiment(self, experiment: str, result: str = None):
        """Record an experiment."""
        entry = {"experiment": experiment}
        if result:
            entry["result"] = result
        self.write("experiment", str(entry), ["experiment"])
    
    def recover(self, recovery: str):
        """Record a recovery."""
        self.write("recovery", recovery, ["recover"])
    
    def get_entries(self, entry_type: str = None, tags: List[str] = None, limit: int = 50) -> List[Dict]:
        """Get journal entries."""
        entries = self._entries
        if entry_type:
            entries = [e for e in entries if e["type"] == entry_type]
        if tags:
            entries = [e for e in entries if any(t in e.get("tags", []) for t in tags)]
        return entries[-limit:]
    
    def get_today_summary(self) -> Dict:
        """Get today's journal summary."""
        types = {}
        for e in self._entries:
            t = e["type"]
            types[t] = types.get(t, 0) + 1
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_entries": len(self._entries),
            "by_type": types
        }


_journal: Optional[Journal] = None


def get_journal() -> Journal:
    global _journal
    if _journal is None:
        _journal = Journal()
    return _journal
