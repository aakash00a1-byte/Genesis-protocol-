"""Dream Mode - GLUTTONY Presence Layer

Sandbox processing during idle time: summarize memories, connect ideas, generate insights."""

import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field


@dataclass
class DreamInsight:
    """An insight generated during dream mode."""
    id: str
    type: str  # 'connection', 'summary', 'pattern', 'prediction'
    title: str
    description: str
    source_items: List[str] = field(default_factory=list)
    created_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class DreamMode:
    """Sandbox processing during idle time."""
    
    def __init__(self, idle_threshold_seconds: int = 300,
                 processing_interval: int = 60):
        self.idle_threshold = idle_threshold_seconds
        self.processing_interval = processing_interval
        self.last_activity = time.time()
        self.is_active = False
        self.is_processing = False
        self.insights: List[DreamInsight] = []
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: List[Callable] = []
        
        # Memory references for processing
        self._timeline_ref = None
        self._relationship_ref = None
        self._wisdom_ref = None
        self._journal_ref = None
    
    def set_memory_references(self, timeline=None, relationship=None,
                            wisdom=None, journal=None):
        """Set references to other memory systems."""
        self._timeline_ref = timeline
        self._relationship_ref = relationship
        self._wisdom_ref = wisdom
        self._journal_ref = journal
    
    def record_activity(self):
        """Record user activity to reset idle timer."""
        self.last_activity = time.time()
    
    def is_idle(self) -> bool:
        """Check if system is idle."""
        return (time.time() - self.last_activity) > self.idle_threshold
    
    def get_idle_duration(self) -> float:
        """Get seconds since last activity."""
        return time.time() - self.last_activity
    
    def start(self):
        """Start dream mode processing thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """Stop dream mode processing."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
    
    def _process_loop(self):
        """Main processing loop."""
        while self._running:
            if self.is_idle() and not self.is_processing:
                self._run_dream_cycle()
            time.sleep(self.processing_interval)
    
    def _run_dream_cycle(self):
        """Run a single dream processing cycle."""
        self.is_processing = True
        try:
            # Summarize memories
            self._summarize_memories()
            
            # Connect ideas
            self._connect_ideas()
            
            # Generate insights
            self._generate_insights()
            
            # Process journal
            self._process_journal()
            
            self.is_active = True
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(self)
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self.is_processing = False
    
    def _summarize_memories(self):
        """Summarize recent memories."""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'timeline_events': 0,
            'relationship_interactions': 0,
            'wisdom_items': 0,
            'journal_entries': 0
        }
        
        if self._timeline_ref:
            summary['timeline_events'] = len(self._timeline_ref.events)
        
        if self._relationship_ref:
            summary['relationship_interactions'] = self._relationship_ref.interaction_count
        
        if self._wisdom_ref:
            wisdom_stats = self._wisdom_ref.get_wisdom_summary()
            summary['wisdom_items'] = wisdom_stats['facts_count'] + wisdom_stats['beliefs_count']
        
        if self._journal_ref:
            summary['journal_entries'] = len(self._journal_ref.entries)
        
        insight = DreamInsight(
            id=f"dream_{len(self.insights)}_{int(time.time())}",
            type="summary",
            title="Memory Summary",
            description=f"Current state: {summary['timeline_events']} events, "
                       f"{summary['relationship_interactions']} interactions, "
                       f"{summary['wisdom_items']} wisdom items, "
                       f"{summary['journal_entries']} journal entries",
            source_items=["memory_summary"]
        )
        self.insights.append(insight)
        
        # Keep only last 50 insights
        if len(self.insights) > 50:
            self.insights = self.insights[-50:]
    
    def _connect_ideas(self):
        """Connect related ideas across memory systems."""
        connections = []
        
        # Get recent timeline events
        if self._timeline_ref and self._timeline_ref.events:
            recent_events = self._timeline_ref.events[-5:]
            event_types = [e.get('type') for e in recent_events]
            
            # Look for patterns
            if len(event_types) >= 3:
                pattern = self._detect_pattern(event_types)
                if pattern:
                    connections.append(pattern)
        
        # Connect relationship topics with wisdom
        if self._relationship_ref and self._wisdom_ref:
            topics = [t['topic'] for t in self._relationship_ref.long_term_topics[-3:]]
            if topics:
                # Find related wisdom items
                related = []
                for topic in topics:
                    for fact in self._wisdom_ref.facts[-5:]:
                        if topic.lower() in fact['statement'].lower():
                            related.append(fact['id'])
                
                if related:
                    insight = DreamInsight(
                        id=f"dream_{len(self.insights)}_{int(time.time())}",
                        type="connection",
                        title="Topic Connection",
                        description=f"Connected {len(topics)} topics with {len(related)} wisdom items",
                        source_items=topics + related
                    )
                    connections.append(insight)
        
        self.insights.extend(connections)
    
    def _detect_pattern(self, items: List) -> Optional[DreamInsight]:
        """Detect patterns in items."""
        if len(items) < 3:
            return None
        
        # Simple pattern detection
        if items[-1] == items[-2] == items[-3]:
            return DreamInsight(
                id=f"dream_{len(self.insights)}_{int(time.time())}",
                type="pattern",
                title="Repeating Pattern Detected",
                description=f"Same event type occurred 3 times: {items[-1]}",
                source_items=[str(items[-1])]
            )
        return None
    
    def _generate_insights(self):
        """Generate new insights from existing data."""
        insights_generated = 0
        
        # Generate insight about learning
        if self._wisdom_ref and len(self._wisdom_ref.assumptions) > 0:
            assumption = self._wisdom_ref.assumptions[-1]
            insight = DreamInsight(
                id=f"dream_{len(self.insights)}_{int(time.time())}",
                type="prediction",
                title="Assumption to Investigate",
                description=f"Consider verifying: {assumption['statement'][:100]}",
                source_items=[assumption['id']]
            )
            self.insights.append(insight)
            insights_generated += 1
        
        # Generate insight about unknowns
        if self._wisdom_ref:
            unknowns = [u for u in self._wisdom_ref.unknowns 
                       if not u.get('investigated', False)]
            if unknowns:
                insight = DreamInsight(
                    id=f"dream_{len(self.insights)}_{int(time.time())}",
                    type="summary",
                    title="Questions to Explore",
                    description=f"{len(unknowns)} unanswered questions remain",
                    source_items=[u['id'] for u in unknowns[:3]]
                )
                self.insights.append(insight)
                insights_generated += 1
    
    def _process_journal(self):
        """Process journal entries for reflections."""
        if not self._journal_ref or not self._journal_ref.entries:
            return
        
        recent_entries = self._journal_ref.entries[-7:]  # Last week
        failures = [e for e in recent_entries if e.get('entry_type') == 'failure']
        recoveries = [e for e in recent_entries if e.get('entry_type') == 'recovery']
        
        if failures and recoveries:
            insight = DreamInsight(
                id=f"dream_{len(self.insights)}_{int(time.time())}",
                type="pattern",
                title="Recovery Pattern",
                description=f"{len(recoveries)} recoveries from {len(failures)} failures in past week",
                source_items=["journal"]
            )
            self.insights.append(insight)
    
    def add_callback(self, callback: Callable):
        """Add a callback to be notified after dream cycles."""
        self._callbacks.append(callback)
    
    def get_recent_insights(self, limit: int = 10) -> List[Dict]:
        """Get recent dream insights."""
        insights_data = []
        for insight in self.insights[-limit:]:
            insights_data.append({
                'id': insight.id,
                'type': insight.type,
                'title': insight.title,
                'description': insight.description,
                'created_at': insight.created_at
            })
        return insights_data
    
    def get_status(self) -> Dict:
        """Get dream mode status."""
        return {
            'is_active': self.is_active,
            'is_processing': self.is_processing,
            'is_idle': self.is_idle(),
            'idle_duration_seconds': round(self.get_idle_duration()),
            'insights_generated': len(self.insights),
            'recent_insights': self.get_recent_insights(5)
        }


_dream_mode: Optional[DreamMode] = None


def get_dream_mode() -> DreamMode:
    """Get dream mode singleton."""
    global _dream_mode
    if _dream_mode is None:
        _dream_mode = DreamMode()
    return _dream_mode
