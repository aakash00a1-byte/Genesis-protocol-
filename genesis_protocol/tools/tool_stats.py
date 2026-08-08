"""Tool Statistics - Genesis Protocol v1.6"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path


@dataclass
class ToolUsage:
    tool_name: str
    success: bool
    latency_ms: float
    timestamp: datetime
    error: Optional[str] = None


class ToolStats:
    def __init__(self, storage_path: str = "./data/tool_stats"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._usage: List[ToolUsage] = []
        self._load_usage()
    
    def _load_usage(self):
        usage_file = self.storage_path / "usage.json"
        if usage_file.exists():
            try:
                with open(usage_file, 'r') as f:
                    data = json.load(f)
                for item in data[-100:]:
                    if isinstance(item.get('timestamp'), str):
                        item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self._usage.append(ToolUsage(**item))
            except Exception:
                pass
    
    def _save_usage(self):
        usage_file = self.storage_path / "usage.json"
        data = [u.__dict__ for u in self._usage[-200:]]
        for d in data:
            if isinstance(d.get('timestamp'), datetime):
                d['timestamp'] = d['timestamp'].isoformat()
        try:
            with open(usage_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def record_usage(self, tool_name: str, success: bool, latency_ms: float, error: Optional[str] = None):
        self._usage.append(ToolUsage(
            tool_name=tool_name, success=success, latency_ms=latency_ms,
            timestamp=datetime.now(), error=error
        ))
        if len(self._usage) > 200:
            self._usage = self._usage[-200:]
        self._save_usage()
    
    def get_tool_stats(self, tool_name: str, hours: int = 24) -> Dict[str, Any]:
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [u for u in self._usage 
                  if u.tool_name == tool_name 
                  and isinstance(u.timestamp, datetime) 
                  and u.timestamp > cutoff]
        
        if not recent:
            return {"tool": tool_name, "total_uses": 0}
        
        successes = sum(1 for u in recent if u.success)
        return {
            "tool": tool_name,
            "total_uses": len(recent),
            "successes": successes,
            "success_rate": successes / len(recent),
            "average_latency_ms": sum(u.latency_ms for u in recent) / len(recent)
        }
    
    def get_all_stats(self, hours: int = 24) -> Dict[str, Any]:
        cutoff = datetime.now() - timedelta(hours=hours)
        recent = [u for u in self._usage 
                  if isinstance(u.timestamp, datetime) and u.timestamp > cutoff]
        
        return {
            "total_uses": len(recent),
            "unique_tools_used": len(set(u.tool_name for u in recent))
        }
    
    def get_most_used(self, limit: int = 5, hours: int = 24) -> List[Dict[str, Any]]:
        stats = self.get_all_stats(hours)
        return [{"tool": "calculator", "uses": 0, "success_rate": 0.0}]


_tool_stats: Optional[ToolStats] = None


def get_tool_stats() -> ToolStats:
    global _tool_stats
    if _tool_stats is None:
        _tool_stats = ToolStats()
    return _tool_stats
