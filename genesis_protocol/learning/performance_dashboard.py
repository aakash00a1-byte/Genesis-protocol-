"""Performance Dashboard - Genesis Protocol v1.5
Tracks daily usage, latency, memory growth, task completion."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path


@dataclass
class DailyMetrics:
    """Daily performance metrics."""
    date: str
    total_conversations: int
    successful_conversations: int
    average_latency_ms: float
    memory_entries_added: int
    tasks_completed: int
    tasks_failed: int
    average_quality: float


class PerformanceDashboard:
    """Tracks and displays performance metrics."""
    
    def __init__(self, storage_path: str = "./data/performance"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._daily_metrics: Dict[str, DailyMetrics] = {}
        self._load_metrics()
    
    def _load_metrics(self):
        """Load metrics from disk."""
        metrics_file = self.storage_path / "daily_metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                for date, m in data.items():
                    self._daily_metrics[date] = DailyMetrics(**m)
            except Exception:
                pass
    
    def _save_metrics(self):
        """Save metrics to disk."""
        metrics_file = self.storage_path / "daily_metrics.json"
        data = {date: m.__dict__ for date, m in self._daily_metrics.items()}
        try:
            with open(metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def record_daily(
        self,
        conversations: int = 0,
        successful: int = 0,
        latency_ms: float = 0,
        memory_growth: int = 0,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
        quality: float = 0
    ):
        """Record daily metrics."""
        today = datetime.now().strftime('%Y-%m-%d')
        
        if today in self._daily_metrics:
            m = self._daily_metrics[today]
            m.total_conversations += conversations
            m.successful_conversations += successful
            # Recalculate averages
            if m.total_conversations > 0:
                m.average_latency_ms = (m.average_latency_ms * (m.total_conversations - conversations) + latency_ms * conversations) / m.total_conversations
            m.memory_entries_added += memory_growth
            m.tasks_completed += tasks_completed
            m.tasks_failed += tasks_failed
            m.average_quality = (m.average_quality * (m.total_conversations - conversations) + quality * conversations) / max(1, m.total_conversations)
        else:
            self._daily_metrics[today] = DailyMetrics(
                date=today,
                total_conversations=conversations,
                successful_conversations=successful,
                average_latency_ms=latency_ms,
                memory_entries_added=memory_growth,
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                average_quality=quality
            )
        
        self._save_metrics()
    
    def get_daily(self, days: int = 7) -> List[DailyMetrics]:
        """Get daily metrics for the last N days."""
        result = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            if date in self._daily_metrics:
                result.append(self._daily_metrics[date])
        return result
    
    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        daily = self.get_daily(7)
        
        if not daily:
            return {
                'period': '7 days',
                'total_conversations': 0,
                'success_rate': 0,
                'average_latency_ms': 0,
                'memory_growth': 0,
                'task_completion_rate': 0
            }
        
        total_conv = sum(m.total_conversations for m in daily)
        total_success = sum(m.successful_conversations for m in daily)
        total_tasks = sum(m.tasks_completed + m.tasks_failed for m in daily)
        completed_tasks = sum(m.tasks_completed for m in daily)
        total_latency = sum(m.average_latency_ms * m.total_conversations for m in daily)
        total_memory = sum(m.memory_entries_added for m in daily)
        
        return {
            'period': '7 days',
            'days_reporting': len(daily),
            'total_conversations': total_conv,
            'successful_conversations': total_success,
            'success_rate': total_success / max(1, total_conv),
            'average_latency_ms': total_latency / max(1, total_conv),
            'memory_growth': total_memory,
            'tasks_completed': completed_tasks,
            'tasks_total': total_tasks,
            'task_completion_rate': completed_tasks / max(1, total_tasks)
        }
    
    def get_trends(self) -> Dict[str, str]:
        """Get performance trends."""
        weekly = self.get_daily(14)
        
        if len(weekly) < 7:
            return {'status': 'insufficient_data'}
        
        first_week = weekly[7:]
        second_week = weekly[:7]
        
        def avg_conversations(week):
            return sum(m.total_conversations for m in week) / len(week)
        
        def avg_quality(week):
            return sum(m.average_quality * m.total_conversations for m in week) / max(1, sum(m.total_conversations for m in week))
        
        def avg_latency(week):
            total_conv = sum(m.total_conversations for m in week)
            return sum(m.average_latency_ms * m.total_conversations for m in week) / max(1, total_conv)
        
        # Conversations trend
        first_conv = avg_conversations(first_week)
        second_conv = avg_conversations(second_week)
        conv_trend = "improving" if second_conv > first_conv * 1.1 else "declining" if second_conv < first_conv * 0.9 else "stable"
        
        # Quality trend
        first_quality = avg_quality(first_week)
        second_quality = avg_quality(second_week)
        quality_trend = "improving" if second_quality > first_quality + 0.05 else "declining" if second_quality < first_quality - 0.05 else "stable"
        
        # Latency trend
        first_latency = avg_latency(first_week)
        second_latency = avg_latency(second_week)
        latency_trend = "improving" if second_latency < first_latency * 0.9 else "declining" if second_latency > first_latency * 1.1 else "stable"
        
        return {
            'conversation_volume': conv_trend,
            'quality': quality_trend,
            'latency': latency_trend,
            'overall': "improving" if sum([conv_trend == "improving", quality_trend == "improving", latency_trend == "improving"]) >= 2 else "stable"
        }


# Global singleton
_performance_dashboard: Optional[PerformanceDashboard] = None


def get_performance_dashboard() -> PerformanceDashboard:
    """Get global performance dashboard."""
    global _performance_dashboard
    if _performance_dashboard is None:
        _performance_dashboard = PerformanceDashboard()
    return _performance_dashboard
