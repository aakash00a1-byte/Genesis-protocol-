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
        
        # Weather (exact, key-free)
        self.register_tool(Tool(
            name="get_weather",
            description="Get exact current weather for a place. Use when the user asks about weather, temperature or forecast.",
            parameters={
                "location": {"type": "string", "description": "City or place name", "required": True}
            },
            handler=self._tool_get_weather
        ))

        # Currency exchange rate (exact, key-free)
        self.register_tool(Tool(
            name="get_exchange_rate",
            description="Get the exact exchange rate between two currencies. Use when the user asks for a currency conversion rate.",
            parameters={
                "base": {"type": "string", "description": "Base currency code, e.g. USD", "required": True},
                "quote": {"type": "string", "description": "Quote currency code, e.g. INR", "required": True}
            },
            handler=self._tool_get_exchange_rate
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
        """Web search: Tavily when configured, else a key-free fallback.

        The previous version imported ``TavilyIntegration``, a name that does
        not exist, so every call raised ImportError and no search ever ran.
        """
        query = params.get("query", "")
        if not query:
            return ToolResult(False, error="No query provided")

        errors = []

        # Preferred: Tavily, when an API key is configured.
        try:
            from genesis_protocol.integrations.tavily_integration import TavilyClient
            tavily = TavilyClient()
            if tavily.is_configured():
                result = await tavily.search(query)
                if result.get("results"):
                    from genesis_protocol.integrations.source_credibility import assess
                    labelled = assess(result.get("results", []))
                    return ToolResult(True, data={
                        "results": labelled,
                        "answer": result.get("answer", ""),
                        "source": "tavily",
                    })
                errors.append(f"tavily: {result.get('error') or 'no results'}")
            else:
                errors.append("tavily: not configured")
        except Exception as e:
            errors.append(f"tavily: {e}")

        # Fallback: key-free providers, so live data still works without a key.
        try:
            from genesis_protocol.integrations.key_free_search import get_key_free_search
            fallback = await get_key_free_search().search(query)
            if fallback.get("results"):
                from genesis_protocol.integrations.source_credibility import assess
                labelled = assess(fallback["results"])
                return ToolResult(True, data={
                    "results": labelled,
                    "answer": "",
                    "source": fallback.get("source", "key_free"),
                })
            errors.append(f"key_free: {fallback.get('error')}")
        except Exception as e:
            errors.append(f"key_free: {e}")

        return ToolResult(False, error="Web search failed: " + "; ".join(errors))
    
    async def _tool_get_weather(self, params: Dict) -> ToolResult:
        """Exact current weather via a key-free provider."""
        from genesis_protocol.integrations.live_facts import get_weather

        data = await get_weather(params.get("location", ""))
        if data.get("error"):
            return ToolResult(False, error=data["error"])
        return ToolResult(True, data=data)

    async def _tool_get_exchange_rate(self, params: Dict) -> ToolResult:
        """Exact reference exchange rate via a key-free provider."""
        from genesis_protocol.integrations.live_facts import get_exchange_rate

        data = await get_exchange_rate(params.get("base", ""), params.get("quote", ""))
        if data.get("error"):
            return ToolResult(False, error=data["error"])
        return ToolResult(True, data=data)

    async def _tool_memory_store(self, params: Dict) -> ToolResult:
        """Store an approved fact in the user's own memory.

        Storage is per-user. It previously wrote to a global bucket
        (``user_id=0``), which would have mixed one user's facts into every
        other user's recall. Without a user id we refuse rather than write
        somewhere shared.
        """
        key = params.get("key", "")
        value = params.get("value", "")
        user_id = params.get("user_id") or 0

        if not value:
            return ToolResult(False, error="Missing value")
        if not user_id:
            return ToolResult(
                False,
                error="memory_store needs a user id; refused to write to shared memory",
            )

        try:
            from genesis_protocol.agentic.memory import MemoryRejected, get_agent_memory

            memory = get_agent_memory()
            memory_id = memory.remember(int(user_id), value, kind="fact", approved=True)
            return ToolResult(True, data={"stored": True, "key": key, "id": memory_id})
        except MemoryRejected as e:
            return ToolResult(False, error=f"memory rejected: {e}")
        except Exception as e:
            return ToolResult(False, error=f"Memory store error: {e}")

    async def _tool_memory_recall(self, params: Dict) -> ToolResult:
        """Recall the user's own memories, never another user's."""
        query = params.get("query", "")
        limit = params.get("limit", 5)
        user_id = params.get("user_id") or 0

        if not user_id:
            return ToolResult(False, error="memory_recall needs a user id")

        try:
            from genesis_protocol.agentic.memory import get_agent_memory

            memories = get_agent_memory().recall(int(user_id), query, limit=limit)
            return ToolResult(True, data={"results": memories, "count": len(memories)})
        except Exception as e:
            return ToolResult(False, error=f"Memory recall error: {e}")

    async def _tool_code_execution(self, params: Dict) -> ToolResult:
        """Execute Python code in the bounded sandbox.

        The previous version ran ``python3 -c`` through a bare ``subprocess.run``:
        no CPU or memory cap, no file-size limit, and the parent's environment
        (including API keys) inherited by the child. It now runs through
        ``agentic.sandbox.run_python``, which applies rlimits, strips secrets
        from the child environment and caps captured output.
        """
        code = params.get("code", "")
        timeout = params.get("timeout", 30)

        if not code:
            return ToolResult(False, error="No code provided")

        try:
            from genesis_protocol.agentic.sandbox import run_python

            result = run_python(code, timeout=float(timeout))
            if result.success:
                return ToolResult(True, data={
                    "output": result.stdout,
                    "error": result.stderr if result.stderr else None,
                    "duration_ms": result.duration_ms,
                    "limits": result.limits,
                })
            if result.error:
                reason = result.error
            elif result.stderr:
                reason = result.stderr
            else:
                reason = (
                    f"execution failed (exit code {result.exit_code}); "
                    f"it may have hit a resource limit "
                    f"(cpu {result.limits.get('cpu_seconds')}s, "
                    f"memory {result.limits.get('memory_mb')}MB)"
                )
            return ToolResult(False, error=reason)
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