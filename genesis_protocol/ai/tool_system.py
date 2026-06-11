"""Genesis Protocol - Tool Calling System

AI Agent tools for autonomous operation:
- web_search (Tavily)
- memory_store
- memory_recall
- code_execution
- file_reader
"""

import asyncio
import json
import logging
import subprocess
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod

from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.tools")


class ToolResult:
    """Result from tool execution."""
    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data = data
        self.error = error
    
    def to_dict(self) -> Dict:
        return {"success": self.success, "data": self.data, "error": self.error}


@dataclass
class Tool:
    """Tool definition."""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


class ToolSystem:
    """
    Tool calling system for AI agent.
    
    Provides autonomous tools that the AI can call to perform actions.
    """
    
    def __init__(self):
        """Initialize tool system."""
        self.tools: Dict[str, Tool] = {}
        self.logger = logging.getLogger("ai.tools")
        self._register_tools()
    
    def _register_tools(self):
        """Register all available tools."""
        # Web Search (Tavily)
        self.register_tool(Tool(
            name="web_search",
            description="Search the web for current information. Use when user asks for news, latest info, or facts.",
            parameters={
                "query": {"type": "string", "description": "Search query", "required": True},
                "depth": {"type": "string", "description": "basic or advanced", "default": "basic"}
            },
            handler=self._tool_web_search
        ))
        
        # Memory Store
        self.register_tool(Tool(
            name="memory_store",
            description="Store important information in long-term memory. Use when user says 'remember' or wants to save info.",
            parameters={
                "key": {"type": "string", "description": "Memory key", "required": True},
                "value": {"type": "string", "description": "Information to store", "required": True},
                "importance": {"type": "float", "description": "Importance 0-1", "default": 0.5}
            },
            handler=self._tool_memory_store
        ))
        
        # Memory Recall
        self.register_tool(Tool(
            name="memory_recall",
            description="Recall stored memories. Use when user asks about past conversations or 'what did I say before'.",
            parameters={
                "query": {"type": "string", "description": "Query to search memories", "required": True},
                "limit": {"type": "int", "description": "Max results", "default": 5}
            },
            handler=self._tool_memory_recall
        ))
        
        # Code Execution
        self.register_tool(Tool(
            name="code_execution",
            description="Execute Python code. Use for calculations, data processing, or coding assistance.",
            parameters={
                "code": {"type": "string", "description": "Python code to execute", "required": True},
                "timeout": {"type": "int", "description": "Max execution time in seconds", "default": 30}
            },
            handler=self._tool_code_execution
        ))
        
        # File Reader
        self.register_tool(Tool(
            name="file_reader",
            description="Read contents of a file. Use when user wants to see code or document content.",
            parameters={
                "path": {"type": "string", "description": "File path to read", "required": True},
                "max_lines": {"type": "int", "description": "Max lines to read", "default": 100}
            },
            handler=self._tool_file_reader
        ))
        
        self.logger.info(f"Registered {len(self.tools)} tools")
    
    def register_tool(self, tool: Tool):
        """Register a new tool."""
        self.tools[tool.name] = tool
        self.logger.debug(f"Registered tool: {tool.name}")
    
    def get_tool_schemas(self) -> List[Dict]:
        """Get tool schemas for LLM function calling."""
        schemas = []
        for name, tool in self.tools.items():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
            for param_name, param_info in tool.parameters.items():
                schema["function"]["parameters"]["properties"][param_name] = {
                    "type": param_info.get("type", "string"),
                    "description": param_info.get("description", "")
                }
                if param_info.get("required", False):
                    schema["function"]["parameters"]["required"].append(param_name)
            
            schemas.append(schema)
        return schemas
    
    async def execute_tool(self, tool_name: str, parameters: Dict) -> ToolResult:
        """Execute a tool by name with parameters."""
        tool = self.tools.get(tool_name)
        if not tool:
            return ToolResult(False, error=f"Unknown tool: {tool_name}")
        
        try:
            self.logger.info(f"Executing tool: {tool_name} with params: {parameters}")
            result = await tool.handler(parameters)
            return result
        except Exception as e:
            self.logger.error(f"Tool execution error: {tool_name} - {e}")
            return ToolResult(False, error=str(e))
    
    async def execute_multiple(self, tool_calls: List[Dict]) -> List[ToolResult]:
        """Execute multiple tool calls."""
        results = []
        for call in tool_calls:
            tool_name = call.get("name")
            parameters = call.get("parameters", {})
            result = await self.execute_tool(tool_name, parameters)
            results.append(result)
        return results
    
    # Tool Implementations
    
    async def _tool_web_search(self, params: Dict) -> ToolResult:
        """Web search using Tavily."""
        query = params.get("query", "")
        depth = params.get("depth", "basic")
        
        if not query:
            return ToolResult(False, error="No query provided")
        
        try:
            from genesis_protocol.integrations.tavily_integration import TavilyIntegration
            tavily = TavilyIntegration()
            result = await tavily.search(query, depth=depth)
            
            if result.get("success"):
                return ToolResult(True, data={
                    "results": result.get("results", []),
                    "answer": result.get("answer", "")
                })
            else:
                return ToolResult(False, error=result.get("error", "Search failed"))
        except Exception as e:
            return ToolResult(False, error=f"Web search error: {e}")
    
    async def _tool_memory_store(self, params: Dict) -> ToolResult:
        """Store in memory."""
        key = params.get("key", "")
        value = params.get("value", "")
        importance = params.get("importance", 0.5)
        
        if not key or not value:
            return ToolResult(False, error="Missing key or value")
        
        try:
            from genesis_protocol.memory.unified_memory import get_unified_memory
            memory = get_unified_memory()
            # Store with timestamp
            memory.long_term.store(
                chat_id=0,  # Global storage
                user_id=0,
                content=f"{key}: {value}",
                memory_type="stored_knowledge",
                importance=importance
            )
            return ToolResult(True, data={"stored": True, "key": key})
        except Exception as e:
            return ToolResult(False, error=f"Memory store error: {e}")
    
    async def _tool_memory_recall(self, params: Dict) -> ToolResult:
        """Recall from memory."""
        query = params.get("query", "")
        limit = params.get("limit", 5)
        
        if not query:
            return ToolResult(False, error="No query provided")
        
        try:
            from genesis_protocol.memory.unified_memory import get_unified_memory
            memory = get_unified_memory()
            results = memory.long_term.recall(query, limit=limit)
            
            return ToolResult(True, data={
                "memories": results,
                "count": len(results)
            })
        except Exception as e:
            return ToolResult(False, error=f"Memory recall error: {e}")
    
    async def _tool_code_execution(self, params: Dict) -> ToolResult:
        """Execute Python code."""
        code = params.get("code", "")
        timeout = params.get("timeout", 30)
        
        if not code:
            return ToolResult(False, error="No code provided")
        
        try:
            # Execute code with timeout
            result = subprocess.run(
                ["python3", "-c", code],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return ToolResult(True, data={
                    "output": result.stdout,
                    "error": result.stderr if result.stderr else None
                })
            else:
                return ToolResult(False, error=result.stderr or "Execution failed")
        except subprocess.TimeoutExpired:
            return ToolResult(False, error=f"Code execution timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, error=f"Execution error: {e}")
    
    async def _tool_file_reader(self, params: Dict) -> ToolResult:
        """Read file contents."""
        path = params.get("path", "")
        max_lines = params.get("max_lines", 100)
        
        if not path:
            return ToolResult(False, error="No path provided")
        
        try:
            # Security: Prevent path traversal
            if ".." in path or path.startswith("/"):
                return ToolResult(False, error="Invalid path")
            
            with open(path, "r") as f:
                lines = f.readlines()[:max_lines]
            
            return ToolResult(True, data={
                "content": "".join(lines),
                "lines_read": len(lines),
                "truncated": len(lines) >= max_lines
            })
        except FileNotFoundError:
            return ToolResult(False, error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(False, error=f"Read error: {e}")


# Singleton
_tool_system: Optional[ToolSystem] = None


def get_tool_system() -> ToolSystem:
    """Get or create tool system singleton."""
    global _tool_system
    if _tool_system is None:
        _tool_system = ToolSystem()
    return _tool_system