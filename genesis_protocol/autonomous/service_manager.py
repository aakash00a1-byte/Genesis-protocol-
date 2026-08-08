"""Service Manager - Genesis Protocol v1.3
Manages all autonomous background services."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("autonomous.service_manager")


class AutonomousServiceManager:
    """Manages all autonomous background services."""

    def __init__(self):
        self._started = False
        self._start_time = datetime.now()
        self._services: Dict[str, bool] = {
            'event_logger': False,
            'autonomous_daemon': False,
            'reflection_engine': False,
            'mood_engine': False,
            'user_profile_manager': False
        }

    def start_all(self):
        """Start all autonomous services."""
        if self._started:
            logger.warning("Services already started")
            return

        logger.info("Starting all autonomous services...")

        # Start event logger
        try:
            from .event_system import get_event_logger
            event_logger = get_event_logger()
            event_logger.log(
                event_logger.EventType.STARTUP if hasattr(event_logger, 'EventType') else None,
                "Genesis Protocol v1.3 starting up",
                severity="info"
            )
            self._services['event_logger'] = True
        except Exception as e:
            logger.error(f"Failed to start event logger: {e}")

        # Start autonomous daemon
        try:
            from .autonomous_daemon import get_autonomous_daemon
            daemon = get_autonomous_daemon()
            daemon.start()
            self._services['autonomous_daemon'] = True
        except Exception as e:
            logger.error(f"Failed to start autonomous daemon: {e}")

        # Initialize reflection engine
        try:
            from .reflection_engine import get_reflection_engine
            reflection = get_reflection_engine()
            self._services['reflection_engine'] = True
        except Exception as e:
            logger.error(f"Failed to initialize reflection engine: {e}")

        # Initialize mood engine (it's per-user, so just mark as available)
        self._services['mood_engine'] = True

        # Initialize user profile manager
        try:
            from .user_profile import get_user_profile_manager
            profile_mgr = get_user_profile_manager()
            self._services['user_profile_manager'] = True
        except Exception as e:
            logger.error(f"Failed to initialize user profile manager: {e}")

        self._started = True
        self._start_time = datetime.now()
        logger.info("All autonomous services started")

    def stop_all(self):
        """Stop all autonomous services."""
        logger.info("Stopping all autonomous services...")

        # Stop daemon
        try:
            from .autonomous_daemon import get_autonomous_daemon
            daemon = get_autonomous_daemon()
            daemon.stop()
        except Exception as e:
            logger.error(f"Failed to stop daemon: {e}")

        self._started = False
        logger.info("All autonomous services stopped")

    def get_status(self) -> Dict[str, Any]:
        """Get status of all services."""
        uptime = (datetime.now() - self._start_time).total_seconds() if self._started else 0

        return {
            'running': self._started,
            'uptime_seconds': uptime,
            'services': self._services.copy(),
            'start_time': self._start_time.isoformat()
        }

    def get_full_state(self) -> Dict[str, Any]:
        """Get full autonomous state for /state endpoint."""
        state = {
            'timestamp': datetime.now().isoformat(),
            'running': self._started,
            'uptime_seconds': (datetime.now() - self._start_time).total_seconds() if self._started else 0
        }

        # Get persona info
        try:
            from genesis_protocol.personality import get_personality_engine
            engine = get_personality_engine(0)
            state['persona'] = engine.current_persona.value
        except Exception:
            state['persona'] = 'unknown'

        # Get mood info
        try:
            from .mood_engine import get_mood_engine
            mood = get_mood_engine(0)
            state['mood'] = mood.current_mood.value
        except Exception:
            state['mood'] = 'unknown'

        # Get task queue stats
        try:
            from genesis_protocol.tasks import TaskQueue
            queue = TaskQueue()
            stats = queue.get_stats()
            state['tasks_pending'] = stats.get('pending', 0)
            state['tasks_total'] = stats.get('total', 0)
        except Exception:
            state['tasks_pending'] = 0
            state['tasks_total'] = 0

        # Get memory stats
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            state['memories'] = sum(1 for _ in ltm._memory_index.values()) if hasattr(ltm, '_memory_index') else 0
        except Exception:
            state['memories'] = 0

        # Get health info
        try:
            from .event_system import get_event_logger
            events = get_event_logger()
            stats = events.get_stats()
            state['health'] = {
                'status': 'ok' if stats.get('by_severity', {}).get('error', 0) == 0 else 'warning',
                'events_last_hour': stats.get('last_hour', 0),
                'errors': stats.get('by_severity', {}).get('error', 0)
            }
        except Exception:
            state['health'] = {'status': 'unknown'}

        # Get event stats
        try:
            from .event_system import get_event_logger
            events = get_event_logger()
            state['event_count'] = events.get_stats().get('total', 0)
        except Exception:
            state['event_count'] = 0

        return state


# Global singleton
_service_manager: Optional[AutonomousServiceManager] = None


def get_service_manager() -> AutonomousServiceManager:
    """Get global service manager."""
    global _service_manager
    if _service_manager is None:
        _service_manager = AutonomousServiceManager()
    return _service_manager
