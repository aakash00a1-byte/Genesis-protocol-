"""Cost Tracker - GLUTTONY v3.0 Survival Layer"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class CostTracker:
    def __init__(self, storage_path: str = "./data/survival"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._costs = []
        self._total_cost = 0.0
        self._load()
    
    def _load(self):
        f = self.storage_path / "costs.json"
        if f.exists():
            data = json.load(open(f))
            self._costs = data.get("costs", [])
            self._total_cost = data.get("total", 0.0)
    
    def _save(self):
        f = self.storage_path / "costs.json"
        json.dump({"costs": self._costs, "total": self._total_cost}, open(f, 'w'))
    
    def track(self, provider: str, tokens_used: int, cost: float, model: str = ""):
        entry = {"timestamp": datetime.now().isoformat(), "provider": provider, "model": model, "tokens": tokens_used, "cost": cost}
        self._costs.append(entry)
        self._total_cost += cost
        self._save()
    
    def get_total(self) -> float:
        return self._total_cost
    
    def get_by_provider(self, provider: str) -> float:
        return sum(e["cost"] for e in self._costs if e["provider"] == provider)
    
    def get_today(self) -> float:
        today = datetime.now().date().isoformat()
        return sum(e["cost"] for e in self._costs if e["timestamp"].startswith(today))


_cost_tracker = None
def get_cost_tracker() -> CostTracker:
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = CostTracker()
    return _cost_tracker
