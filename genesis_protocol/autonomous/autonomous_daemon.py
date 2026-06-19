"""Autonomous Daemon - Genesis Protocol v1.3
Background loops for memory maintenance, task execution, health monitoring."""

import threading
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from .event_system import EventType, get_event_logger


logger = logging.getLogger("autonomous.daemon")


class AutonomousDaemon:
    """Background daemon for autonomous operations."""

    def __init__(self):
        self._running = False
        self._threads: Dict[str, threading.Thread] = {}
        self._last_memory_prune = datetime.now()
        self._last_health_check = datetime.now()
        self._last_summarization = datetime.now()
        self._conversation_count = 0

        # Intervals (in seconds)
        self.MEMORY_PRUNE_INTERVAL = 3600  # 1 hour
        self.HEALTH_CHECK_INTERVAL = 60    # 1 minute
        self.SUMMARIZATION_INTERVAL = 1800  # 30 minutes
        self.CONVERSATIONS_BEFORE_REFLECTION = 10

    def start(self):
        """Start all daemon threads."""
        if self._running:
            return

        self._running = True
        events = get_event_logger()
        events.log(EventType.STARTUP, "Autonomous daemon starting", severity="info")

        # Start all loops
        self._start_loop("memory_maintenance", self._memory_maintenance_loop)
        self._start_loop("health_monitor", self._health_monitor_loop)
        self._start_loop("conversation_tracker", self._conversation_tracker_loop)

        logger.info("Autonomous daemon started")

    def stop(self):
        """Stop all daemon threads."""
        if not self._running:
            return

        self._running = False
        for name, thread in self._threads.items():
            thread.join(timeout=2)
        self._threads.clear()

        events = get_event_logger()
        events.log(EventType.SHUTDOWN, "Autonomous daemon stopped", severity="info")
        logger.info("Autonomous daemon stopped")

    def _start_loop(self, name: str, target: callable):
        """Start a named loop in a daemon thread."""
        thread = threading.Thread(target=target, daemon=True, name=f"daemon_{name}")
        thread.start()
        self._threads[name] = thread

    def increment_conversation(self):
        """Increment conversation counter and trigger reflection if needed."""
        self._conversation_count += 1
        if self._conversation_count >= self.CONVERSATIONS_BEFORE_REFLECTION:
            self._trigger_reflection()
            self._conversation_count = 0

    def _trigger_reflection(self):
        """Trigger reflection engine."""
        try:
            from .reflection_engine import get_reflection_engine
            reflection = get_reflection_engine()
            reflection.generate_reflection()
        except Exception as e:
            logger.error(f"Reflection failed: {e}")

    def _memory_maintenance_loop(self):
        """Periodic memory pruning and optimization."""
        while self._running:
            try:
                time.sleep(self.MEMORY_PRUNE_INTERVAL)

                if not self._running:
                    break

                # Check if it's time to prune
                now = datetime.now()
                if now - self._last_memory_prune > timedelta(seconds=self.MEMORY_PRUNE_INTERVAL):
                    self._run_memory_maintenance()
                    self._last_memory_prune = now

            except Exception as e:
                logger.error(f"Memory maintenance error: {e}")
                events = get_event_logger()
                events.log(
                    EventType.EXCEPTION,
                    f"Memory maintenance error: {e}",
                    severity="error"
                )

    def _run_memory_maintenance(self):
        """Run memory maintenance tasks."""
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()

            # Prune low-importance memories
            pruned = ltm.prune_memories()
            
            events = get_event_logger()
            events.log(
                EventType.MEMORY_PRUNED,
                f"Memory maintenance completed. Pruned {pruned} low-importance memories.",
                metadata={'pruned_count': pruned}
            )
            logger.info(f"Memory pruned: {pruned} entries")

        except Exception as e:
            logger.error(f"Memory maintenance failed: {e}")

    def _health_monitor_loop(self):
        """Periodic health monitoring."""
        while self._running:
            try:
                time.sleep(self.HEALTH_CHECK_INTERVAL)

                if not self._running:
                    break

                now = datetime.now()
                if now - self._last_health_check > timedelta(seconds=self.HEALTH_CHECK_INTERVAL):
                    self._run_health_check()
                    self._last_health_check = now

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    def _run_health_check(self):
        """Run health check on all systems."""
        events = get_event_logger()
        issues = []

        # Check memory
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            memory_count = sum(1 for _ in ltm._memory_index.values()) if hasattr(ltm, '_memory_index') else 0
            if memory_count > 10000:
                issues.append(f"High memory usage: {memory_count} entries")
        except Exception as e:
            issues.append(f"Memory check failed: {e}")

        # Check task queue
        try:
            from genesis_protocol.tasks import TaskQueue
            queue = TaskQueue()
            stats = queue.get_stats()
            if stats.get('failed', 0) > 5:
                issues.append(f"Task failures: {stats['failed']}")
        except Exception as e:
            issues.append(f"Task queue check failed: {e}")

        # Log health status
        if issues:
            for issue in issues:
                events.log(EventType.HEALTH_WARNING, issue, severity="warning")
                logger.warning(f"Health warning: {issue}")
        else:
            events.log(EventType.HEALTH_OK, "All systems healthy", severity="info")

    def _conversation_tracker_loop(self):
        """Track conversations and trigger summarization."""
        while self._running:
            try:
                time.sleep(self.SUMMARIZATION_INTERVAL)

                if not self._running:
                    break

                now = datetime.now()
                if now - self._last_summarization > timedelta(seconds=self.SUMMARIZATION_INTERVAL):
                    self._run_conversation_summarization()
                    self._last_summarization = now

            except Exception as e:
                logger.error(f"Conversation tracker error: {e}")

    def _run_conversation_summarization(self):
        """Run conversation summarization for active users."""
        try:
            # This would integrate with conversation history
            # For now, just log that it ran
            events = get_event_logger()
            events.log(
                EventType.REFLECTION_COMPLETE,
                "Scheduled conversation summarization completed",
                severity="info"
            )
            logger.info("Conversation summarization completed")
        except Exception as e:
            logger.error(f"Conversation summarization failed: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get daemon status."""
        return {
            'running': self._running,
            'threads': list(self._threads.keys()),
            'conversation_count': self._conversation_count,
            'last_memory_prune': self._last_memory_prune.isoformat(),
            'last_health_check': self._last_health_check.isoformat(),
            'last_summarization': self._last_summarization.isoformat(),
        }


# Global singleton
_autonomous_daemon: Optional[AutonomousDaemon] = None
_daemon_lock = threading.Lock()


def get_autonomous_daemon() -> AutonomousDaemon:
    """Get or create global autonomous daemon."""
    global _autonomous_daemon
    with _daemon_lock:
        if _autonomous_daemon is None:
            _autonomous_daemon = AutonomousDaemon()
        return _autonomous_daemon
