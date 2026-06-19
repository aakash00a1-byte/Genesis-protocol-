"""Reflection Cycle - Genesis Protocol v1.5
Self-assessment every N conversations."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path


@dataclass
class Reflection:
    """A self-reflection."""
    id: str
    conversation_count: int
    timestamp: datetime
    what_worked: List[str]
    what_failed: List[str]
    what_to_remember: List[str]
    what_to_improve: List[str]
    quality_trend: str  # improving, stable, declining
    confidence_score: float


class ReflectionCycle:
    """Generates self-reflections periodically."""
    
    def __init__(self, storage_path: str = "./data/reflections", interval: int = 10):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.interval = interval  # Generate reflection every N conversations
        self._conversations_since_reflection = 0
        self._reflections: List[Reflection] = []
        self._load_reflections()
    
    def _load_reflections(self):
        """Load reflections from disk."""
        refl_file = self.storage_path / "reflections.json"
        if refl_file.exists():
            try:
                with open(refl_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    self._reflections.append(Reflection(**item))
            except Exception:
                pass
    
    def _save_reflections(self):
        """Save reflections to disk."""
        refl_file = self.storage_path / "reflections.json"
        data = [r.__dict__ for r in self._reflections[-50:]]  # Keep last 50
        for d in data:
            if isinstance(d.get('timestamp'), datetime):
                d['timestamp'] = d['timestamp'].isoformat()
        try:
            with open(refl_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def record_conversation(self, quality_score: float = 1.0):
        """Record a conversation for reflection tracking."""
        self._conversations_since_reflection += 1
    
    def should_reflect(self) -> bool:
        """Check if it's time for a reflection."""
        return self._conversations_since_reflection >= self.interval
    
    def generate_reflection(
        self,
        recent_evaluations: List[Any] = None
    ) -> Reflection:
        """Generate a self-reflection."""
        reflection_id = f"refl_{len(self._reflections) + 1}_{datetime.now().strftime('%Y%m%d')}"
        
        # Analyze recent performance
        what_worked = []
        what_failed = []
        what_to_remember = []
        what_to_improve = []
        
        # Get evaluation data
        try:
            from .evaluation_engine import get_evaluation_engine
            eval_engine = get_evaluation_engine()
            recent = eval_engine.get_recent_evaluations(limit=self.interval)
            
            # Analyze successes
            successful = [e for e in recent if e.success]
            if successful:
                avg_quality = sum(e.quality_score for e in successful) / len(successful)
                if avg_quality > 0.7:
                    what_worked.append(f"High quality responses ({avg_quality:.0%} average)")
                if len(successful) > self.interval * 0.8:
                    what_worked.append("High success rate")
            
            # Analyze failures
            failed = [e for e in recent if not e.success]
            for f in failed:
                if f.error_message:
                    what_failed.append(f"Error: {f.error_message[:50]}")
            
            # Calculate quality trend
            if len(recent) >= 5:
                first_half = recent[:len(recent)//2]
                second_half = recent[len(recent)//2:]
                first_avg = sum(e.quality_score for e in first_half) / len(first_half)
                second_avg = sum(e.quality_score for e in second_half) / len(second_half)
                
                if second_avg > first_avg + 0.1:
                    quality_trend = "improving"
                    what_to_remember.append("Quality is improving - keep doing what works")
                elif second_avg < first_avg - 0.1:
                    quality_trend = "declining"
                    what_to_improve.append("Quality declining - need to investigate causes")
                else:
                    quality_trend = "stable"
                    what_to_remember.append("Quality is stable")
            else:
                quality_trend = "stable"
            
            # Generate improvements
            if any(e.latency_ms > 5000 for e in recent):
                what_to_improve.append("Reduce response latency")
            if any(not e.success for e in recent[-3:]):
                what_failed.append("Recent failures need attention")
                
        except Exception:
            quality_trend = "stable"
        
        # Add default improvements
        if not what_to_improve:
            what_to_improve.append("Continue monitoring quality metrics")
        
        # Create reflection
        reflection = Reflection(
            id=reflection_id,
            conversation_count=len(self._reflections) * self.interval,
            timestamp=datetime.now(),
            what_worked=what_worked or ["General helpfulness"],
            what_failed=what_failed or [],
            what_to_remember=what_to_remember or ["User satisfaction is important"],
            what_to_improve=what_to_improve,
            quality_trend=quality_trend,
            confidence_score=0.7
        )
        
        self._reflections.append(reflection)
        self._conversations_since_reflection = 0
        self._save_reflections()
        
        # Store in long-term memory
        self._store_reflection_in_memory(reflection)
        
        return reflection
    
    def _store_reflection_in_memory(self, reflection: Reflection):
        """Store reflection in long-term memory."""
        try:
            from genesis_protocol.memory import get_long_term_memory, MemoryImportance
            
            ltm = get_long_term_memory()
            
            content = f"[Reflection] Quality trend: {reflection.quality_trend}. "
            content += f"What worked: {', '.join(reflection.what_worked[:2])}. "
            content += f"Improvements needed: {', '.join(reflection.what_to_improve[:2])}"
            
            ltm.add_memory(
                content=content,
                user_id=0,  # System reflection
                importance=MemoryImportance.MEDIUM,
                category="reflection"
            )
        except Exception:
            pass
    
    def get_recent_reflections(self, limit: int = 5) -> List[Reflection]:
        """Get recent reflections."""
        return self._reflections[-limit:]
    
    def get_latest_reflection(self) -> Optional[Reflection]:
        """Get the latest reflection."""
        if self._reflections:
            return self._reflections[-1]
        return None
    
    def get_reflection_insights(self) -> Dict[str, Any]:
        """Get aggregated insights from all reflections."""
        if not self._reflections:
            return {'has_reflections': False}
        
        all_worked = []
        all_failed = []
        all_improve = []
        trends = []
        
        for r in self._reflections:
            all_worked.extend(r.what_worked)
            all_failed.extend(r.what_failed)
            all_improve.extend(r.what_to_improve)
            trends.append(r.quality_trend)
        
        # Count most common items
        def most_common(lst, n=3):
            from collections import Counter
            return [item for item, _ in Counter(lst).most_common(n)]
        
        return {
            'has_reflections': True,
            'total_reflections': len(self._reflections),
            'most_common_successes': most_common(all_worked),
            'most_common_failures': most_common(all_failed),
            'most_common_improvements': most_common(all_improve),
            'quality_trends': trends[-5:],
            'overall_trend': trends[-1] if trends else 'stable'
        }


# Global singleton
_reflection_cycle: Optional[ReflectionCycle] = None


def get_reflection_cycle() -> ReflectionCycle:
    """Get global reflection cycle."""
    global _reflection_cycle
    if _reflection_cycle is None:
        _reflection_cycle = ReflectionCycle()
    return _reflection_cycle
