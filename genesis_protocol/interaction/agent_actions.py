"""Agent Actions - Genesis Protocol v1.4
Allow AI to perform actions like creating tasks, saving memories, etc."""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger("interaction.agent_actions")


class AgentActionType(Enum):
    """Types of agent actions."""
    CREATE_TASK = "create_task"
    SAVE_MEMORY = "save_memory"
    SEARCH_MEMORY = "search_memory"
    SUMMARIZE = "summarize"
    CALL_TOOL = "call_tool"
    SET_PERSONA = "set_persona"
    SET_MOOD = "set_mood"
    CREATE_REMINDER = "create_reminder"


@dataclass
class AgentAction:
    """An action the AI can perform."""
    action_type: AgentActionType
    parameters: Dict[str, Any]
    result: Optional[Any] = None
    timestamp: datetime = None
    success: bool = False


class AgentActionHandler:
    """Handles agent actions."""
    
    def __init__(self):
        self.action_history: List[AgentAction] = []
    
    def execute_action(self, action_type: str, parameters: Dict[str, Any], user_id: int = 0) -> Dict[str, Any]:
        """Execute an agent action."""
        try:
            action = AgentAction(
                action_type=AgentActionType(action_type),
                parameters=parameters,
                timestamp=datetime.now()
            )
            
            if action_type == "create_task":
                result = self._create_task(parameters, user_id)
            elif action_type == "save_memory":
                result = self._save_memory(parameters, user_id)
            elif action_type == "search_memory":
                result = self._search_memory(parameters, user_id)
            elif action_type == "summarize":
                result = self._summarize(parameters, user_id)
            elif action_type == "call_tool":
                result = self._call_tool(parameters)
            elif action_type == "set_persona":
                result = self._set_persona(parameters, user_id)
            elif action_type == "set_mood":
                result = self._set_mood(parameters, user_id)
            elif action_type == "create_reminder":
                result = self._create_reminder(parameters, user_id)
            else:
                result = {"success": False, "error": f"Unknown action: {action_type}"}
            
            action.result = result
            action.success = result.get("success", False)
            self.action_history.append(action)
            
            return result
            
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _create_task(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Create a task."""
        try:
            from genesis_protocol.tasks import TaskQueue
            
            queue = TaskQueue()
            task_id = queue.add_task(
                name=params.get("name", "Untitled Task"),
                func_name=params.get("func_name", ""),
                func_args=params.get("args", {}),
                user_id=user_id,
                priority=params.get("priority", 5)
            )
            
            # Log event
            try:
                from genesis_protocol.autonomous import get_event_logger, EventType
                events = get_event_logger()
                events.log(EventType.TASK_CREATED, f"Task created: {params.get('name')}", user_id=user_id)
            except:
                pass
            
            return {
                "success": True,
                "task_id": task_id,
                "message": f"Task '{params.get('name')}' created"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _save_memory(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Save a memory."""
        try:
            from genesis_protocol.memory import get_long_term_memory, MemoryImportance
            
            ltm = get_long_term_memory()
            importance_str = params.get("importance", "medium")
            importance_map = {
                "critical": MemoryImportance.CRITICAL,
                "high": MemoryImportance.HIGH,
                "medium": MemoryImportance.MEDIUM,
                "low": MemoryImportance.LOW
            }
            importance = importance_map.get(importance_str.lower(), MemoryImportance.MEDIUM)
            
            entry_id = ltm.add_memory(
                content=params.get("content", ""),
                user_id=user_id,
                importance=importance,
                category=params.get("category", "general")
            )
            
            # Log event
            try:
                from genesis_protocol.autonomous import get_event_logger, EventType
                events = get_event_logger()
                events.log(EventType.MEMORY_CREATED, f"Memory saved: {params.get('content')[:50]}", user_id=user_id)
            except:
                pass
            
            return {
                "success": True,
                "memory_id": entry_id,
                "message": "Memory saved"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _search_memory(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Search memories."""
        try:
            from genesis_protocol.memory import get_long_term_memory
            
            ltm = get_long_term_memory()
            results = ltm.search(
                params.get("query", ""),
                user_id=user_id,
                limit=params.get("limit", 5)
            )
            
            return {
                "success": True,
                "results": [{"content": r.content, "category": r.category} for r in results],
                "count": len(results)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _summarize(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Summarize conversations."""
        try:
            from genesis_protocol.autonomous import get_reflection_engine
            
            reflection = get_reflection_engine()
            reflection.record_conversation(user_id, params.get("message", ""), params.get("response", ""))
            
            # Generate reflection
            result = reflection.generate_reflection(user_id)
            
            return {
                "success": True,
                "summary": result.get("summary", ""),
                "learnings": result.get("learnings", [])
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _call_tool(self, params: Dict) -> Dict[str, Any]:
        """Call a tool."""
        try:
            from .tool_system import get_tool_registry
            
            registry = get_tool_registry()
            result = registry.execute_tool(
                params.get("tool_name", ""),
                params.get("parameters", {})
            )
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _set_persona(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Set persona."""
        try:
            from genesis_protocol.personality import get_personality_engine, Persona
            
            engine = get_personality_engine(user_id)
            persona = Persona(params.get("persona", "normal"))
            response = engine.set_persona(persona)
            
            return {
                "success": True,
                "message": response
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _set_mood(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Set mood."""
        try:
            from genesis_protocol.autonomous import get_mood_engine, Mood
            
            mood_engine = get_mood_engine(user_id)
            mood = Mood(params.get("mood", "calm"))
            response = mood_engine.set_mood(mood, "AI requested")
            
            return {
                "success": True,
                "message": response
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _create_reminder(self, params: Dict, user_id: int) -> Dict[str, Any]:
        """Create a reminder."""
        try:
            from .tool_system import get_tool_registry
            
            registry = get_tool_registry()
            result = registry.execute_tool("reminder", {
                "time": params.get("time", "1h"),
                "message": params.get("message", ""),
                "user_id": user_id
            })
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_action_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get action history."""
        return [
            {
                "type": a.action_type.value,
                "parameters": a.parameters,
                "success": a.success,
                "timestamp": a.timestamp.isoformat() if a.timestamp else None
            }
            for a in self.action_history[-limit:]
        ]


# Global singleton
_agent_handler: Optional[AgentActionHandler] = None


def get_agent_handler() -> AgentActionHandler:
    """Get global agent action handler."""
    global _agent_handler
    if _agent_handler is None:
        _agent_handler = AgentActionHandler()
    return _agent_handler
