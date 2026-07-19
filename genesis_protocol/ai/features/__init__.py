"""Genesis Protocol - AI Features

Advanced AI capabilities built on top of the core AI system.

Features:
- Context Condenser: Compress long conversations to save tokens
- MCP Client: Connect to Model Context Protocol tool servers
- Parallel Executor: Run independent tools simultaneously
- Streaming Wrapper: Real-time token-by-token output
- Conversation State: Pause, Resume, Fork capabilities
- Agent Delegation: Spawn specialized sub-agents
- Metrics Tracker: Usage, costs, and performance tracking
- Critic: Self-critique and quality evaluation
- Goal Completion: Self-continuing execution loop
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

from genesis_protocol.ai.features.conversation_state import (
    ConversationStateManager,
    ConversationState,
    ConversationSnapshot,
    ConversationCheckpoint,
    get_state_manager
)

from genesis_protocol.ai.features.agent_delegation import (
    AgentDelegationManager,
    SubAgent,
    DelegationTask,
    AgentStatus,
    get_delegation_manager,
    quick_delegate
)

from genesis_protocol.ai.features.metrics_tracker import (
    MetricsTracker,
    LLMUsage,
    TokenUsage,
    CostSummary,
    get_metrics_tracker
)

from genesis_protocol.ai.features.critic import (
    ResponseCritic,
    CritiqueResult,
    CritiqueCriteria,
    CritiqueLevel,
    get_critic
)

from genesis_protocol.ai.features.goal_completion import (
    GoalCompletionLoop,
    Goal,
    GoalResult,
    GoalStatus,
    get_goal_loop
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
    
    # Conversation State
    "ConversationStateManager",
    "ConversationState",
    "ConversationSnapshot",
    "ConversationCheckpoint",
    "get_state_manager",
    
    # Agent Delegation
    "AgentDelegationManager",
    "SubAgent",
    "DelegationTask",
    "AgentStatus",
    "get_delegation_manager",
    "quick_delegate",
    
    # Metrics
    "MetricsTracker",
    "LLMUsage",
    "TokenUsage",
    "CostSummary",
    "get_metrics_tracker",
    
    # Critic
    "ResponseCritic",
    "CritiqueResult",
    "CritiqueCriteria",
    "CritiqueLevel",
    "get_critic",
    
    # Goal Completion
    "GoalCompletionLoop",
    "Goal",
    "GoalResult",
    "GoalStatus",
    "get_goal_loop",
]
