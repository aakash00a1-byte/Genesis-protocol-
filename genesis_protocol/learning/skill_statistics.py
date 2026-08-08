"""Skill Statistics - Genesis Protocol v1.5"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path


@dataclass
class SkillMetric:
    skill_name: str
    value: float
    timestamp: datetime
    context: str = ""


class SkillStats:
    def __init__(self, storage_path: str = "./data/skills"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._metrics: Dict[str, List[SkillMetric]] = {}
        self._load_metrics()

    def _load_metrics(self):
        metrics_file = self.storage_path / "metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                for skill, metrics in data.items():
                    self._metrics[skill] = []
                    for m in metrics[-100:]:
                        if isinstance(m.get('timestamp'), str):
                            m['timestamp'] = datetime.fromisoformat(m['timestamp'])
                        self._metrics[skill].append(SkillMetric(**m))
            except Exception:
                pass

    def _save_metrics(self):
        metrics_file = self.storage_path / "metrics.json"
        data = {}
        for skill, metrics in self._metrics.items():
            data[skill] = [m.__dict__ for m in metrics[-100:]]
            for m in data[skill]:
                if isinstance(m.get('timestamp'), datetime):
                    m['timestamp'] = m['timestamp'].isoformat()
        with open(metrics_file, 'w') as f:
            json.dump(data, f, indent=2)

    def record_coding_accuracy(self, correct: bool, context: str = ""):
        self._record_metric("coding_accuracy", 1.0 if correct else 0.0, context)

    def record_memory_recall(self, recalled: bool, context: str = ""):
        self._record_metric("memory_recall", 1.0 if recalled else 0.0, context)

    def record_task_completion(self, completed: bool, context: str = ""):
        self._record_metric("task_completion", 1.0 if completed else 0.0, context)

    def _record_metric(self, skill: str, value: float, context: str):
        if skill not in self._metrics:
            self._metrics[skill] = []
        self._metrics[skill].append(SkillMetric(skill_name=skill, value=value, timestamp=datetime.now(), context=context))
        if len(self._metrics[skill]) > 100:
            self._metrics[skill] = self._metrics[skill][-100:]
        self._save_metrics()

    def get_skill_score(self, skill: str, hours: int = 24) -> float:
        if skill not in self._metrics:
            return 0.0
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [m for m in self._metrics[skill] if isinstance(m.timestamp, datetime) and m.timestamp > cutoff]
        if not recent:
            return 0.0
        return sum(m.value for m in recent) / len(recent)

    def get_all_scores(self, hours: int = 24) -> Dict[str, float]:
        return {skill: self.get_skill_score(skill, hours) for skill in self._metrics.keys()}

    def get_strengths(self, threshold: float = 0.7) -> List[str]:
        scores = self.get_all_scores(hours=24)
        return [skill for skill, score in scores.items() if score >= threshold]

    def get_weaknesses(self, threshold: float = 0.5) -> List[str]:
        scores = self.get_all_scores(hours=24)
        return [skill for skill, score in scores.items() if score < threshold]

    def get_stats(self) -> Dict[str, Any]:
        return {
            'skills': list(self._metrics.keys()),
            'scores_24h': self.get_all_scores(hours=24),
            'strengths': self.get_strengths(),
            'weaknesses': self.get_weaknesses()
        }


_skill_stats: Optional[SkillStats] = None


def get_skill_statistics() -> SkillStats:
    global _skill_stats
    if _skill_stats is None:
        _skill_stats = SkillStats()
    return _skill_stats
