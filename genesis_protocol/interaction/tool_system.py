"""Tool System - Genesis Protocol v1.4
Dynamic tool registration and execution."""

import re
import json
import math
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger("interaction.tools")


@dataclass
class ToolDefinition:
    """Definition of a tool."""
    name: str
    description: str
    parameters: Dict[str, str]  # param_name -> description
    function: Callable
    category: str = "general"


class Tool(ABC):
    """Base class for tools."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        pass
    
    @property
    def category(self) -> str:
        return "general"
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the tool with given parameters."""
        pass
    
    def get_definition(self) -> ToolDefinition:
        """Get tool definition for registration."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={},
            function=lambda **kw: self.execute(**kw),
            category=self.category
        )


class CalculatorTool(Tool):
    """Mathematical calculator tool."""
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return "Perform mathematical calculations. Input: expression (e.g., '2+2', 'sqrt(16)', 'sin(pi/2)')"
    
    @property
    def category(self) -> str:
        return "utility"
    
    def execute(self, expression: str) -> Dict[str, Any]:
        """Execute calculation."""
        try:
            # Safe evaluation
            expr = expression.replace('^', '**')
            expr = expr.replace('sqrt', 'math.sqrt')
            expr = expr.replace('sin', 'math.sin')
            expr = expr.replace('cos', 'math.cos')
            expr = expr.replace('tan', 'math.tan')
            expr = expr.replace('log', 'math.log')
            expr = expr.replace('pi', str(math.pi))
            expr = expr.replace('e', str(math.e))
            
            result = eval(expr, {"__builtins__": {}}, math.__dict__)
            
            return {
                'success': True,
                'expression': expression,
                'result': result,
                'type': type(result).__name__
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class NotesTool(Tool):
    """Notes and snippets storage tool."""
    
    def __init__(self):
        self._notes: Dict[str, Dict] = {}
    
    @property
    def name(self) -> str:
        return "notes"
    
    @property
    def description(self) -> str:
        return "Store and retrieve notes. Actions: save, get, list, delete"
    
    @property
    def category(self) -> str:
        return "productivity"
    
    def execute(self, action: str, key: str = "", content: str = "") -> Dict[str, Any]:
        """Execute notes action."""
        if action == "save":
            self._notes[key] = {
                'content': content,
                'created_at': datetime.now().isoformat()
            }
            return {'success': True, 'message': f'Saved note: {key}'}
        
        elif action == "get":
            if key in self._notes:
                return {'success': True, 'note': self._notes[key]}
            return {'success': False, 'error': f'Note not found: {key}'}
        
        elif action == "list":
            return {'success': True, 'notes': list(self._notes.keys())}
        
        elif action == "delete":
            if key in self._notes:
                del self._notes[key]
                return {'success': True, 'message': f'Deleted note: {key}'}
            return {'success': False, 'error': f'Note not found: {key}'}
        
        return {'success': False, 'error': 'Unknown action'}


class ReminderTool(Tool):
    """Reminder creation tool."""
    
    @property
    def name(self) -> str:
        return "reminder"
    
    @property
    def description(self) -> str:
        return "Create reminders. Input: time (e.g., '1h', '30m', '1d'), message"
    
    @property
    def category(self) -> str:
        return "productivity"
    
    def execute(self, time: str, message: str, user_id: int = 0) -> Dict[str, Any]:
        """Create a reminder."""
        try:
            # Parse time
            match = re.match(r'(\d+)\s*(m|h|d)', time.lower())
            if not match:
                return {'success': False, 'error': 'Invalid time format'}
            
            amount, unit = match.groups()
            multipliers = {'m': 60, 'h': 3600, 'd': 86400}
            delay_seconds = int(amount) * multipliers[unit]
            
            # Create task
            from genesis_protocol.tasks import TaskQueue, TaskStatus
            queue = TaskQueue()
            
            task_id = queue.add_task(
                name=f"Reminder: {message[:50]}",
                func_name="reminder",
                func_args={'message': message},
                user_id=user_id,
                priority=5
            )
            
            return {
                'success': True,
                'message': f'Reminder set for {time}: {message}',
                'task_id': task_id,
                'delay_seconds': delay_seconds
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class HistorySearchTool(Tool):
    """Search conversation history tool."""
    
    @property
    def name(self) -> str:
        return "history_search"
    
    @property
    def description(self) -> str:
        return "Search conversation history. Input: query, limit (default 5)"
    
    @property
    def category(self) -> str:
        return "memory"
    
    def execute(self, query: str, limit: int = 5, user_id: int = 0) -> Dict[str, Any]:
        """Search history."""
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            
            results = ltm.search(query, user_id=user_id, limit=limit)
            
            return {
                'success': True,
                'query': query,
                'results': [{'content': r.content, 'category': r.category} for r in results],
                'count': len(results)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class MemorySearchTool(Tool):
    """Search memories tool."""
    
    @property
    def name(self) -> str:
        return "memory_search"
    
    @property
    def description(self) -> str:
        return "Search long-term memories. Input: query, limit (default 5)"
    
    @property
    def category(self) -> str:
        return "memory"
    
    def execute(self, query: str, limit: int = 5, user_id: int = 0) -> Dict[str, Any]:
        """Search memories."""
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            
            results = ltm.search(query, user_id=user_id, limit=limit)
            
            return {
                'success': True,
                'query': query,
                'memories': [{'content': r.content, 'importance': r.importance} for r in results],
                'count': len(results)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class FileReaderTool(Tool):
    """Read files tool."""
    
    @property
    def name(self) -> str:
        return "file_reader"
    
    @property
    def description(self) -> str:
        return "Read file contents. Input: path (relative to project root)"
    
    @property
    def category(self) -> str:
        return "utility"
    
    def execute(self, path: str, max_lines: int = 100) -> Dict[str, Any]:
        """Read file."""
        try:
            import os
            # Security: only allow reading within project
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            full_path = os.path.join(base_path, path)
            full_path = os.path.normpath(full_path)
            
            # Ensure path is within base
            if not full_path.startswith(base_path):
                return {'success': False, 'error': 'Path outside project'}
            
            with open(full_path, 'r') as f:
                lines = f.readlines()[:max_lines]
            
            return {
                'success': True,
                'path': path,
                'content': ''.join(lines),
                'lines': len(lines)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class WebSearchTool(Tool):
    """Web search tool (basic implementation)."""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Search the web. Input: query"
    
    @property
    def category(self) -> str:
        return "information"
    
    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Perform web search."""
        try:
            from genesis_protocol.ai.provider_chain import get_provider_chain
            chain = get_provider_chain()
            
            # Use Groq for search-like functionality
            prompt = f"Search query: {query}\n\nProvide 5 concise, relevant results."
            response = chain.generate(prompt)
            
            return {
                'success': True,
                'query': query,
                'results': response[:500]  # Limit response
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


class ToolRegistry:
    """Registry for all available tools."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register default tools."""
        self.register(CalculatorTool())
        self.register(NotesTool())
        self.register(ReminderTool())
        self.register(HistorySearchTool())
        self.register(MemorySearchTool())
        self.register(FileReaderTool())
        self.register(WebSearchTool())
    
    def register(self, tool: Tool):
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")
    
    def unregister(self, name: str):
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def get_all_tools(self) -> List[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def get_tools_by_category(self, category: str) -> List[Tool]:
        """Get tools by category."""
        return [t for t in self._tools.values() if t.category == category]
    
    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get all tool definitions for AI."""
        return [
            {
                'name': t.name,
                'description': t.description,
                'category': t.category
            }
            for t in self._tools.values()
        ]
    
    def execute_tool(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool."""
        tool = self.get_tool(name)
        if not tool:
            return {'success': False, 'error': f'Tool not found: {name}'}
        
        try:
            return tool.execute(**params)
        except Exception as e:
            return {'success': False, 'error': str(e)}


# Global singleton
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry
