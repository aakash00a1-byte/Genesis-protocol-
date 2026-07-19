"""Genesis Protocol - AI Features

Advanced AI capabilities built on top of the core AI system.

Features:
- Context Condenser: Compress long conversations to save tokens
- MCP Client: Connect to Model Context Protocol tool servers
- Parallel Executor: Run independent tools simultaneously
- Streaming Wrapper: Real-time token-by-token output
"""

from genesis_protocol.ai.features.context_condenser import (
    ContextCondenser,
    CondensedMessage,
    CondensationResult,
    get_condenser
)

from genesis_protocol.ai.features.mcp_client import (
    MCPClient,
    MCPServer,
    MCPTool,
    MCPToolResult,
    MCPConnectionState,
    get_mcp_client,
    DEFAULT_MCP_SERVERS
)

from genesis_protocol.ai.features.parallel_executor import (
    ParallelToolExecutor,
    ParallelResult,
    ToolTask,
    ToolStatus,
    run_parallel,
    can_parallelize
)

from genesis_protocol.ai.features.streaming_wrapper import (
    StreamingWrapper,
    StreamEvent,
    StreamEventType,
    StreamConfig,
    websocket_chat_stream,
    sse_chat_stream
)


__all__ = [
    # Context Condenser
    "ContextCondenser",
    "CondensedMessage",
    "CondensationResult",
    "get_condenser",
    
    # MCP Client
    "MCPClient",
    "MCPServer",
    "MCPTool",
    "MCPToolResult",
    "MCPConnectionState",
    "get_mcp_client",
    "DEFAULT_MCP_SERVERS",
    
    # Parallel Executor
    "ParallelToolExecutor",
    "ParallelResult",
    "ToolTask",
    "ToolStatus",
    "run_parallel",
    "can_parallelize",
    
    # Streaming
    "StreamingWrapper",
    "StreamEvent",
    "StreamEventType",
    "StreamConfig",
    "websocket_chat_stream",
    "sse_chat_stream",
]
