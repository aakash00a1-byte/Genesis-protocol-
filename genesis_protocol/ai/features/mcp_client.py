"""Genesis Protocol - MCP Client Integration

Model Context Protocol (MCP) client for connecting to external tool servers.
Based on OpenHands MCP integration pattern.

MCP enables dynamic tool integration from external servers.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from enum import Enum

logger = logging.getLogger("ai.mcp_client")


class MCPConnectionState(Enum):
    """MCP server connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPTool:
    """MCP Tool definition."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    server_id: str


@dataclass
class MCPToolResult:
    """Result from MCP tool execution."""
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0


@dataclass
class MCPServer:
    """MCP Server configuration."""
    name: str
    url: str
    headers: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    state: MCPConnectionState = MCPConnectionState.DISCONNECTED
    tools: List[MCPTool] = field(default_factory=list)
    _client: Any = None


class MCPClient:
    """
    MCP Client for connecting to external tool servers.
    
    Supports:
    - Multiple MCP servers simultaneously
    - Tool discovery and listing
    - Tool execution with proper formatting
    - Connection management
    """
    
    def __init__(self):
        """Initialize MCP client."""
        self._servers: Dict[str, MCPServer] = {}
        self._tools_cache: Dict[str, MCPTool] = {}
        logger.info("MCP Client initialized")
    
    async def connect_server(self, name: str, url: str, headers: Dict[str, str] = None) -> bool:
        """
        Connect to an MCP server.
        
        Args:
            name: Server name/identifier
            url: Server URL (http/https)
            headers: Optional authentication headers
            
        Returns:
            True if connected successfully
        """
        if name in self._servers:
            logger.warning(f"Server {name} already connected")
            return True
        
        server = MCPServer(
            name=name,
            url=url,
            headers=headers or {},
            state=MCPConnectionState.CONNECTING
        )
        
        try:
            # MCP uses JSON-RPC over HTTP
            import httpx
            server._client = httpx.AsyncClient(
                base_url=url,
                headers=headers,
                timeout=30
            )
            
            # Discover tools
            tools = await self._discover_tools(server)
            server.tools = tools
            server.state = MCPConnectionState.CONNECTED
            
            # Cache tools
            for tool in tools:
                self._tools_cache[f"{name}.{tool.name}"] = tool
            
            self._servers[name] = server
            logger.info(f"Connected to MCP server: {name} ({len(tools)} tools)")
            return True
            
        except Exception as e:
            server.state = MCPConnectionState.ERROR
            logger.error(f"Failed to connect to MCP server {name}: {e}")
            return False
    
    async def disconnect_server(self, name: str):
        """Disconnect from an MCP server."""
        if name in self._servers:
            server = self._servers[name]
            if server._client:
                await server._client.aclose()
            del self._servers[name]
            
            # Remove tools from cache
            self._tools_cache = {
                k: v for k, v in self._tools_cache.items()
                if v.server_name != name
            }
            logger.info(f"Disconnected from MCP server: {name}")
    
    async def _discover_tools(self, server: MCPServer) -> List[MCPTool]:
        """Discover available tools on a server."""
        try:
            # MCP protocol: list_tools
            response = await server._client.post("/", json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1
            })
            
            if response.status_code == 200:
                data = response.json()
                tools = []
                for t in data.get("result", {}).get("tools", []):
                    tools.append(MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        input_schema=t.get("inputSchema", {}),
                        server_name=server.name,
                        server_id=server.name
                    ))
                return tools
            
        except Exception as e:
            logger.error(f"Tool discovery failed for {server.name}: {e}")
        
        return []
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """
        Call an MCP tool.
        
        Args:
            tool_name: Tool name (can include server prefix like "server.tool")
            arguments: Tool arguments
            
        Returns:
            MCPToolResult with execution result
        """
        import time
        start = time.time()
        
        # Parse server.tool format
        if "." in tool_name and tool_name.split(".")[0] in self._servers:
            server_name, actual_tool = tool_name.split(".", 1)
        else:
            # Search in cache
            found = None
            for key, tool in self._tools_cache.items():
                if tool.name == tool_name:
                    found = tool
                    break
            if not found:
                return MCPToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"Tool not found: {tool_name}"
                )
            server_name = found.server_name
            actual_tool = tool_name
        
        if server_name not in self._servers:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Server not connected: {server_name}"
            )
        
        server = self._servers[server_name]
        
        try:
            # MCP protocol: tools/call
            response = await server._client.post("/", json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": actual_tool,
                    "arguments": arguments
                },
                "id": 2
            })
            
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {})
                
                return MCPToolResult(
                    tool_name=tool_name,
                    success=True,
                    result=result,
                    execution_time_ms=int((time.time() - start) * 1000)
                )
            else:
                return MCPToolResult(
                    tool_name=tool_name,
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text}",
                    execution_time_ms=int((time.time() - start) * 1000)
                )
                
        except Exception as e:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000)
            )
    
    def list_tools(self) -> List[MCPTool]:
        """List all available tools from all servers."""
        return list(self._tools_cache.values())
    
    def get_tools_by_server(self, server_name: str) -> List[MCPTool]:
        """Get tools from a specific server."""
        return [
            t for t in self._tools_cache.values()
            if t.server_name == server_name
        ]
    
    def get_servers(self) -> List[Dict[str, Any]]:
        """Get status of all connected servers."""
        return [
            {
                "name": s.name,
                "url": s.url,
                "state": s.state.value,
                "tool_count": len(s.tools)
            }
            for s in self._servers.values()
        ]
    
    async def close(self):
        """Close all connections."""
        for name in list(self._servers.keys()):
            await self.disconnect_server(name)


# Singleton
_mcp_client: Optional[MCPClient] = None


def get_mcp_client() -> MCPClient:
    """Get global MCP client instance."""
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClient()
    return _mcp_client


# Example: Pre-configured popular MCP servers
DEFAULT_MCP_SERVERS = {
    "filesystem": {
        "url": "http://localhost:3001",
        "description": "Local filesystem operations"
    },
    "github": {
        "url": "http://localhost:3002", 
        "description": "GitHub API operations"
    },
    "database": {
        "url": "http://localhost:3003",
        "description": "Database operations"
    }
}
