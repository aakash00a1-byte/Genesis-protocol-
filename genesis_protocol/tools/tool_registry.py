"""Tool Registry - Genesis Protocol v1.6
Dynamic tool registration and management."""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import logging

logger = logging.getLogger("tools.registry")


class ToolPermission(Enum):
    """Tool permission levels."""
    SAFE = "safe"        # Always allowed
    RESTRICTED = "restricted"  # Requires approval
    ADMIN = "admin"      # Admin only


@dataclass
class ToolMetadata:
    """Metadata for a tool."""
    name: str
    description: str
    category: str
    permission: ToolPermission
    parameters: Dict[str, str] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    enabled: bool = True


class Tool:
    """Base class for all tools."""
    
    @property
    def name(self) -> str:
        raise NotImplementedError
    
    @property
    def description(self) -> str:
        raise NotImplementedError
    
    @property
    def category(self) -> str:
        return "general"
    
    @property
    def permission(self) -> ToolPermission:
        return ToolPermission.SAFE
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {}
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        raise NotImplementedError
    
    def get_metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name=self.name,
            description=self.description,
            category=self.category,
            permission=self.permission,
            parameters=self.parameters
        )


class CalculatorTool(Tool):
    """Mathematical calculator tool."""
    
    @property
    def name(self) -> str:
        return "calculator"
    
    @property
    def description(self) -> str:
        return "Perform mathematical calculations"
    
    @property
    def category(self) -> str:
        return "utility"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {"expression": "Math expression (e.g., 2+2, sqrt(16))"}
    
    def execute(self, expression: str) -> Dict[str, Any]:
        import math
        try:
            expr = expression.replace('^', '**')
            expr = expr.replace('sqrt', 'math.sqrt')
            expr = expr.replace('sin', 'math.sin')
            expr = expr.replace('cos', 'math.cos')
            expr = expr.replace('tan', 'math.tan')
            expr = expr.replace('log', 'math.log')
            expr = expr.replace('pi', str(math.pi))
            expr = expr.replace('e', str(math.e))
            
            result = eval(expr, {"__builtins__": {}}, math.__dict__)
            
            return {"success": True, "expression": expression, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}


class WebSearchTool(Tool):
    """Web search tool."""
    
    @property
    def name(self) -> str:
        return "web_search"
    
    @property
    def description(self) -> str:
        return "Search the web for information"
    
    @property
    def category(self) -> str:
        return "information"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {"query": "Search query"}
    
    def execute(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            from genesis_protocol.ai.provider_chain import get_provider_chain
            chain = get_provider_chain()
            response = chain.generate(f"Search query: {query}\n\nProvide 5 concise results.")
            return {"success": True, "query": query, "results": response[:500]}
        except Exception as e:
            return {"success": False, "error": str(e)}


class NotesTool(Tool):
    """Notes management tool."""
    
    def __init__(self):
        self._notes: Dict[str, Dict] = {}
    
    @property
    def name(self) -> str:
        return "notes"
    
    @property
    def description(self) -> str:
        return "Save and retrieve notes"
    
    @property
    def category(self) -> str:
        return "productivity"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {
            "action": "save/get/list/delete",
            "key": "Note identifier",
            "content": "Note content (for save)"
        }
    
    def execute(self, action: str, key: str = "", content: str = "") -> Dict[str, Any]:
        if action == "save":
            self._notes[key] = {"content": content, "created_at": datetime.now().isoformat()}
            return {"success": True, "message": f"Note '{key}' saved"}
        elif action == "get":
            if key in self._notes:
                return {"success": True, "note": self._notes[key]}
            return {"success": False, "error": f"Note '{key}' not found"}
        elif action == "list":
            return {"success": True, "notes": list(self._notes.keys())}
        elif action == "delete":
            if key in self._notes:
                del self._notes[key]
                return {"success": True, "message": f"Note '{key}' deleted"}
            return {"success": False, "error": f"Note '{key}' not found"}
        return {"success": False, "error": "Unknown action"}


class MemorySearchTool(Tool):
    """Search long-term memory."""
    
    @property
    def name(self) -> str:
        return "memory_search"
    
    @property
    def description(self) -> str:
        return "Search long-term memories"
    
    @property
    def category(self) -> str:
        return "memory"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {"query": "Search query", "limit": "Max results (default 5)"}
    
    def execute(self, query: str, limit: int = 5, user_id: int = 0) -> Dict[str, Any]:
        try:
            from genesis_protocol.memory import get_long_term_memory
            ltm = get_long_term_memory()
            results = ltm.search(query, user_id=user_id, limit=limit)
            return {
                "success": True,
                "query": query,
                "memories": [{"content": r.content, "category": r.category} for r in results],
                "count": len(results)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class TaskManagerTool(Tool):
    """Task management tool."""
    
    @property
    def name(self) -> str:
        return "task_manager"
    
    @property
    def description(self) -> str:
        return "Manage tasks"
    
    @property
    def category(self) -> str:
        return "productivity"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {
            "action": "create/list/complete/delete",
            "name": "Task name",
            "priority": "Priority 1-10"
        }
    
    def execute(self, action: str, name: str = "", priority: int = 5, user_id: int = 0) -> Dict[str, Any]:
        try:
            from genesis_protocol.tasks import TaskQueue, TaskStatus
            
            queue = TaskQueue()
            
            if action == "create":
                task_id = queue.add_task(name=name, user_id=user_id, priority=priority)
                return {"success": True, "task_id": task_id, "message": f"Task '{name}' created"}
            
            elif action == "list":
                tasks = queue.get_user_tasks(user_id)
                return {
                    "success": True,
                    "tasks": [{"id": t.id, "name": t.name, "status": t.status.value} for t in tasks]
                }
            
            elif action == "complete":
                queue.update_status(task_id=user_id, new_status=TaskStatus.COMPLETED)
                return {"success": True, "message": "Task completed"}
            
            return {"success": False, "error": "Unknown action"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class HistorySearchTool(Tool):
    """Search conversation history."""
    
    @property
    def name(self) -> str:
        return "history_search"
    
    @property
    def description(self) -> str:
        return "Search conversation history"
    
    @property
    def category(self) -> str:
        return "memory"
    
    def execute(self, query: str, limit: int = 5, user_id: int = 0) -> Dict[str, Any]:
        return MemorySearchTool().execute(query, limit, user_id)


class FileReaderTool(Tool):
    """Read files tool."""
    
    @property
    def name(self) -> str:
        return "file_reader"
    
    @property
    def description(self) -> str:
        return "Read file contents"
    
    @property
    def category(self) -> str:
        return "utility"
    
    @property
    def parameters(self) -> Dict[str, str]:
        return {"path": "File path (relative to project root)"}
    
    def execute(self, path: str, max_lines: int = 100) -> Dict[str, Any]:
        import os
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            full_path = os.path.normpath(os.path.join(base_path, path))
            
            if not full_path.startswith(base_path):
                return {"success": False, "error": "Path outside project"}
            
            with open(full_path, 'r') as f:
                content = ''.join(f.readlines()[:max_lines])
            
            return {"success": True, "path": path, "content": content, "lines": len(content.splitlines())}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ImageAnalyzerTool(Tool):
    """Image analysis tool."""
    
    @property
    def name(self) -> str:
        return "image_analyzer"
    
    @property
    def description(self) -> str:
        return "Analyze images"
    
    @property
    def category(self) -> str:
        return "vision"
    
    @property
    def permission(self) -> ToolPermission:
        return ToolPermission.SAFE
    
    def execute(self, image_data: bytes = None, prompt: str = "Describe this image", user_id: int = 0) -> Dict[str, Any]:
        if not image_data:
            return {"success": False, "error": "No image data provided"}
        
        try:
            from genesis_protocol.interaction import get_vision_pipeline
            pipeline = get_vision_pipeline()
            analysis = pipeline.analyze_image(image_data, prompt, user_id)
            
            if analysis:
                return {"success": True, "description": analysis.description, "image_id": analysis.image_id}
            return {"success": False, "error": "Analysis failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ToolRegistry:
    """Central registry for all tools."""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._metadata: Dict[str, ToolMetadata] = {}
        self._disabled_tools: set = set()
        self._register_builtin_tools()
    
    def _register_builtin_tools(self):
        """Register all built-in tools."""
        tools = [
            CalculatorTool(),
            WebSearchTool(),
            NotesTool(),
            MemorySearchTool(),
            TaskManagerTool(),
            HistorySearchTool(),
            FileReaderTool(),
            ImageAnalyzerTool(),
        ]
        
        for tool in tools:
            self.register(tool)
    
    def register(self, tool: Tool):
        """Register a new tool."""
        self._tools[tool.name] = tool
        self._metadata[tool.name] = tool.get_metadata()
        logger.info(f"Registered tool: {tool.name}")
    
    def unregister(self, name: str):
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            del self._metadata[name]
            logger.info(f"Unregistered tool: {name}")
    
    def enable(self, name: str):
        """Enable a tool."""
        self._disabled_tools.discard(name)
        if name in self._metadata:
            self._metadata[name].enabled = True
    
    def disable(self, name: str):
        """Disable a tool."""
        self._disabled_tools.add(name)
        if name in self._metadata:
            self._metadata[name].enabled = False
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        if name in self._disabled_tools:
            return None
        return self._tools.get(name)
    
    def is_enabled(self, name: str) -> bool:
        """Check if a tool is enabled."""
        return name not in self._disabled_tools
    
    def get_all_tools(self) -> List[Tool]:
        """Get all registered tools."""
        return [t for name, t in self._tools.items() if name not in self._disabled_tools]
    
    def get_enabled_tools(self) -> List[ToolMetadata]:
        """Get metadata for enabled tools."""
        return [m for name, m in self._metadata.items() if name not in self._disabled_tools]
    
    def get_tools_by_category(self, category: str) -> List[Tool]:
        """Get tools by category."""
        return [t for t in self.get_all_tools() if t.category == category]
    
    def get_tools_by_permission(self, permission: ToolPermission) -> List[Tool]:
        """Get tools by permission level."""
        return [t for t in self.get_all_tools() if t.permission == permission]
    
    def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool."""
        tool = self.get_tool(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' not found or disabled"}
        
        try:
            result = tool.execute(**params)
            result["tool_used"] = name
            return result
        except Exception as e:
            return {"success": False, "error": str(e), "tool_used": name}


# Global singleton
_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """Get global tool registry."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
