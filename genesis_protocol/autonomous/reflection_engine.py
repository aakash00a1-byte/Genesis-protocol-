"""Reflection Engine - Genesis Protocol v1.3
Generates self-reflections and learns from conversations."""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .event_system import EventType, get_event_logger


logger = logging.getLogger("autonomous.reflection")


class ReflectionEngine:
    """Generates reflections and learns from conversations."""

    REFLECTION_QUESTIONS = [
        "What important facts did I learn about the user?",
        "What tasks or commitments were made?",
        "What topics were discussed that might be relevant later?",
        "What patterns or preferences did I notice?",
        "What should I remember for future conversations?"
    ]

    def __init__(self):
        self.conversation_count = 0
        self.last_reflection_time = datetime.now()
        self.reflection_count = 0

    def record_conversation(self, user_id: int, message: str, response: str):
        """Record a conversation for future reflection."""
        self.conversation_count += 1
        logger.debug(f"Conversation recorded. Total: {self.conversation_count}")

    def generate_reflection(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Generate a self-reflection based on recent conversations."""
        events = get_event_logger()

        reflection = {
            'timestamp': datetime.now().isoformat(),
            'conversation_count': self.conversation_count,
            'learnings': [],
            'important_facts': [],
            'pending_tasks': [],
            'topics': [],
            'mood_trends': [],
            'summary': ""
        }

        # Get recent memory events
        recent_events = events.get_events(limit=50)

        # Analyze events for insights
        memory_events = [e for e in recent_events if e.type == EventType.MEMORY_CREATED]
        task_events = [e for e in recent_events if e.type in [
            EventType.TASK_CREATED, EventType.TASK_COMPLETED, EventType.TASK_FAILED
        ]]

        # Extract learnings
        for event in memory_events:
            if event.message:
                reflection['learnings'].append(event.message)

        # Extract important facts
        for event in memory_events:
            if event.metadata and event.metadata.get('importance') >= 4:
                reflection['important_facts'].append(event.message)

        # Extract pending tasks
        for event in task_events:
            if event.type == EventType.TASK_CREATED:
                reflection['pending_tasks'].append(event.message)

        # Generate summary
        reflection['summary'] = self._generate_summary(reflection)

        # Store in long-term memory
        self._store_reflection(reflection, user_id)

        # Log reflection
        events.log(
            EventType.REFLECTION_COMPLETE,
            f"Reflection generated. {len(reflection['important_facts'])} facts learned.",
            user_id=user_id,
            metadata={'learnings': len(reflection['learnings'])}
        )

        self.last_reflection_time = datetime.now()
        self.reflection_count += 1

        logger.info(f"Reflection #{self.reflection_count} generated")
        return reflection

    def _generate_summary(self, reflection: Dict) -> str:
        """Generate a human-readable summary."""
        parts = []

        if reflection['important_facts']:
            facts = f"Learned {len(reflection['important_facts'])} important facts."
            parts.append(facts)

        if reflection['pending_tasks']:
            tasks = f"{len(reflection['pending_tasks'])} pending tasks."
            parts.append(tasks)

        if reflection['topics']:
            topics = f"Topics: {', '.join(reflection['topics'][:3])}"
            parts.append(topics)

        return " ".join(parts) if parts else "No significant insights this cycle."

    def _store_reflection(self, reflection: Dict, user_id: Optional[int]):
        """Store reflection in long-term memory."""
        try:
            from genesis_protocol.memory import get_long_term_memory, MemoryImportance
            
            ltm = get_long_term_memory()

            # Store important facts
            for fact in reflection.get('important_facts', []):
                if fact:
                    ltm.add_memory(
                        content=f"[Reflection] {fact}",
                        user_id=user_id or 0,
                        importance=MemoryImportance.HIGH,
                        category="reflection"
                    )

            # Store summary
            if reflection.get('summary'):
                ltm.add_memory(
                    content=f"[Daily Summary] {reflection['summary']}",
                    user_id=user_id or 0,
                    importance=MemoryImportance.MEDIUM,
                    category="summary"
                )

            logger.debug("Reflection stored in long-term memory")

        except Exception as e:
            logger.error(f"Failed to store reflection: {e}")

    def answer_self_question(self, question: str, user_id: int) -> str:
        """Answer questions about self-knowledge."""
        events = get_event_logger()

        question_lower = question.lower()

        # What did I learn?
        if "learned" in question_lower or "remember" in question_lower:
            memories = []
            try:
                from genesis_protocol.memory import get_long_term_memory
                ltm = get_long_term_memory()
                recent = ltm.get_recent(user_id, limit=5)
                memories = [m.content for m in recent if m.category == "reflection"]
            except Exception:
                pass

            if memories:
                return "Based on my reflections:\n- " + "\n- ".join(memories[:3])
            return "I haven't learned much about you yet. Let's chat!"

        # What tasks?
        if "task" in question_lower or "todo" in question_lower or "pending" in question_lower:
            tasks = []
            try:
                from genesis_protocol.tasks import TaskQueue
                queue = TaskQueue()
                user_tasks = queue.get_user_tasks(user_id)
                pending = [t for t in user_tasks if t.status.value == "pending"]
                tasks = [f"• {t.name}: {t.description}" for t in pending[:3]]
            except Exception:
                pass

            if tasks:
                return f"Pending tasks:\n" + "\n".join(tasks)
            return "No pending tasks!"

        # What's my name?
        if "name" in question_lower and ("my" in question_lower or "me" in question_lower):
            try:
                from genesis_protocol.memory import get_long_term_memory
                ltm = get_long_term_memory()
                results = ltm.search("user name", user_id=user_id, limit=1)
                if results:
                    return f"Your name is: {results[0].content}"
            except Exception:
                pass
            return "I don't know your name yet. Tell me and I'll remember!"

        # What were we talking about?
        if "topic" in question_lower or "discuss" in question_lower or "about" in question_lower:
            try:
                from genesis_protocol.memory import get_long_term_memory
                ltm = get_long_term_memory()
                recent = ltm.get_recent(user_id, limit=3)
                if recent:
                    topics = [m.content for m in recent if m.category == "conversation"]
                    if topics:
                        return f"We were discussing: {topics[0]}"
            except Exception:
                pass
            return "I don't recall what we were last discussing."

        return "I'm still learning about you. Ask me something specific!"

    def get_status(self) -> Dict[str, Any]:
        """Get reflection engine status."""
        return {
            'conversation_count': self.conversation_count,
            'reflection_count': self.reflection_count,
            'last_reflection': self.last_reflection_time.isoformat()
        }


# Global singleton
_reflection_engine: Optional[ReflectionEngine] = None
_reflection_lock = None


def get_reflection_engine() -> ReflectionEngine:
    """Get or create global reflection engine."""
    global _reflection_engine
    if _reflection_engine is None:
        _reflection_engine = ReflectionEngine()
    return _reflection_engine
