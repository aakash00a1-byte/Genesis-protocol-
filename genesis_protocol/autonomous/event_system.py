"""Event System - Genesis Protocol v1.3
Self-observation system for internal event logging."""

import json
import threading
from enum import Enum
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


class EventType(Enum):
    """Types of internal events."""
    STARTUP = "startup"
    SHUTDOWN = "shutdown"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_SUCCESS = "provider_success"
    TASK_CREATED = "task_created"
    TASK_EXECUTED = "task_executed"
    TASK_FAILED = "task_failed"
    TASK_COMPLETED = "task_completed"
    MEMORY_CREATED = "memory_created"
    MEMORY_ACCESSED = "memory_accessed"
    MEMORY_PRUNED = "memory_pruned"
    CONVERSATION_START = "conversation_start"
    CONVERSATION_END = "conversation_end"
    EXCEPTION = "exception"
    MOOD_CHANGE = "mood_change"
    PERSONA_CHANGE = "persona_change"
    USER_PROFILE_UPDATED = "user_profile_updated"
    REFLECTION_COMPLETE = "reflection_complete"
    HEALTH_WARNING = "health_warning"
    HEALTH_OK = "health_ok"
    MODULE_LOADED = "module_loaded"
    MODULE_ERROR = "module_error"


@dataclass
class Event:
    """An internal system event."""
    id: str
    type: EventType
    timestamp: datetime
    message: str
    user_id: Optional[int] = None
    metadata: Dict[str, Any] = None
    severity: str = "info"  # info, warning, error, critical

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'type': self.type.value,
            'timestamp': self.timestamp.isoformat(),
            'message': self.message,
            'user_id': self.user_id,
            'metadata': self.metadata or {},
            'severity': self.severity
        }


class EventLogger:
    """Thread-safe internal event logger."""

    def __init__(self, max_events: int = 1000, persist_path: str = "./data/events"):
        self.max_events = max_events
        self.persist_path = Path(persist_path)
        self.persist_path.mkdir(parents=True, exist_ok=True)
        self._events: List[Event] = []
        self._lock = threading.RLock()
        self._event_counter = 0
        self._subscribers: List[callable] = []
        self._load_recent_events()

    def _load_recent_events(self):
        """Load recent events from disk."""
        events_file = self.persist_path / "events.json"
        if events_file.exists():
            try:
                with open(events_file, 'r') as f:
                    data = json.load(f)
                for event_data in data[-100:]:  # Load last 100
                    event_data['type'] = EventType(event_data['type'])
                    event_data['timestamp'] = datetime.fromisoformat(event_data['timestamp'])
                    event_data['metadata'] = event_data.get('metadata') or {}
                    self._events.append(Event(**event_data))
            except Exception:
                pass

    def _save_events(self):
        """Save events to disk."""
        events_file = self.persist_path / "events.json"
        data = [e.to_dict() for e in self._events[-self.max_events:]]
        try:
            with open(events_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def _generate_id(self) -> str:
        """Generate unique event ID."""
        self._event_counter += 1
        return f"evt_{datetime.now().strftime('%Y%m%d')}_{self._event_counter:04d}"

    def log(
        self,
        event_type: EventType,
        message: str,
        user_id: Optional[int] = None,
        metadata: Dict[str, Any] = None,
        severity: str = "info"
    ) -> Event:
        """Log an event."""
        event = Event(
            id=self._generate_id(),
            type=event_type,
            timestamp=datetime.now(),
            message=message,
            user_id=user_id,
            metadata=metadata or {},
            severity=severity
        )

        with self._lock:
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events:]
            self._save_events()

        # Notify subscribers
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception:
                pass

        return event

    def subscribe(self, callback: callable):
        """Subscribe to new events."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: callable):
        """Unsubscribe from events."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def get_events(
        self,
        event_type: Optional[EventType] = None,
        user_id: Optional[int] = None,
        limit: int = 50,
        severity: Optional[str] = None
    ) -> List[Event]:
        """Get filtered events."""
        with self._lock:
            events = self._events.copy()

        if event_type:
            events = [e for e in events if e.type == event_type]
        if user_id:
            events = [e for e in events if e.user_id == user_id]
        if severity:
            events = [e for e in events if e.severity == severity]

        return events[-limit:]

    def get_recent(self, limit: int = 20) -> List[Event]:
        """Get recent events."""
        with self._lock:
            return self._events[-limit:].copy()

    def get_stats(self) -> Dict[str, Any]:
        """Get event statistics."""
        with self._lock:
            events = self._events

        stats = {
            'total': len(events),
            'by_type': {},
            'by_severity': {'info': 0, 'warning': 0, 'error': 0, 'critical': 0},
            'last_hour': 0
        }

        from datetime import timedelta
        hour_ago = datetime.now() - timedelta(hours=1)

        for event in events:
            type_name = event.type.value
            stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1
            stats['by_severity'][event.severity] = stats['by_severity'].get(event.severity, 0) + 1
            if event.timestamp > hour_ago:
                stats['last_hour'] += 1

        return stats

    def clear_old_events(self, days: int = 7):
        """Clear events older than specified days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)

        with self._lock:
            self._events = [e for e in self._events if e.timestamp > cutoff]
            self._save_events()


# Global singleton
_event_logger: Optional[EventLogger] = None
_event_logger_lock = threading.RLock()


def get_event_logger() -> EventLogger:
    """Get or create global event logger."""
    global _event_logger
    with _event_logger_lock:
        if _event_logger is None:
            _event_logger = EventLogger()
        return _event_logger
