"""Genesis Protocol - Autonomous AI Agent (v2)

Main orchestrator that ties all components together:
- Task Planner
- Execution Loop
- Quality Judge
- Tool System
- Memory Brain
- Scoring Engine
- Autonomous Mode Switch

Operates in NORMAL or AUTONOMOUS mode.
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from genesis_protocol.ai.scoring_engine import get_scoring_engine, ScoringEngine
from genesis_protocol.ai.task_planner import get_task_planner, TaskPlanner, TaskType
from genesis_protocol.ai.execution_loop import get_execution_loop, ExecutionLoop
from genesis_protocol.ai.quality_judge import get_quality_judge, QualityJudge
from genesis_protocol.ai.autonomous_mode import (
    get_mode_manager, OperationMode, AutonomousModeManager, auto_mode_switch
)
from genesis_protocol.ai.tool_system import get_tool_system, ToolSystem
from genesis_protocol.memory.unified_memory import get_unified_memory, UnifiedMemory
from genesis_protocol.ai.provider_chain import get_provider_chain, AICallResult
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.agent")


@dataclass
class AgentResponse:
    """Complete agent response with metadata."""
    success: bool
    response: str
    mode: str
    model_used: Optional[str] = None
    provider_used: Optional[str] = None
    quality_score: float = 0.0
    planning_active: bool = False
    tools_used: List[str] = None
    memory_used: bool = False
    execution_time_ms: int = 0
    error: Optional[str] = None
    
    def __post_init__(self):
        if self.tools_used is None:
            self.tools_used = []


class GenesisAgent:
    """
    Autonomous AI Agent (v2) for Genesis Protocol.
    
    Capabilities:
    - Intelligent model routing (scoring-based)
    - Multi-step task planning and execution
    - Tool-first intelligence (web search, code, memory)
    - Response quality evaluation and self-correction
    - Memory as context brain (short + long term)
    - Autonomous mode with auto-switching
    
    Modes:
    - NORMAL: Fast chat, no planning
    - AUTONOMOUS: Full agent behavior
    """
    
    def __init__(self):
        """Initialize Genesis Agent v2."""
        self.scoring = get_scoring_engine()
        self.task_planner = get_task_planner()
        self.execution_loop = get_execution_loop()
        self.quality_judge = get_quality_judge()
        self.mode_manager = get_mode_manager()
        self.tool_system = get_tool_system()
        self.memory = get_unified_memory()
        self.provider_chain = get_provider_chain()
        self.logger = logging.getLogger("ai.agent")
        
        # Update Claude availability
        self._update_claude_status()
        
        logger.info("Genesis Agent v2 initialized")
    
    def _update_claude_status(self):
        """Check and update Claude availability."""
        available = self.provider_chain.get_available_providers()
        claude_available = "claude" in available
        
        # Also check config
        try:
            from genesis_protocol.config import get_config
            config = get_config()
            if not config.claude.is_configured():
                claude_available = False
        except:
            pass
        
        self.scoring.set_claude_availability(claude_available)
        logger.info(f"Claude availability: {claude_available}")
    
    async def process(self, query: str, chat_id: int = 0, 
                      user_id: int = 0, force_mode: str = None) -> AgentResponse:
        """
        Process user query through the agent system.
        
        Args:
            query: User query
            chat_id: Telegram chat ID
            user_id: User ID
            force_mode: Force specific mode ('normal' or 'autonomous')
            
        Returns:
            AgentResponse with response and metadata
        """
        start_time = datetime.utcnow()
        tools_used = []
        
        try:
            # Auto-switch or force mode
            if force_mode == "autonomous":
                self.mode_manager.enable_autonomous()
            elif force_mode == "normal":
                self.mode_manager.disable_autonomous()
            else:
                auto_mode_switch(query)
            
            mode = self.mode_manager.current_mode
            is_autonomous = mode == OperationMode.AUTONOMOUS
            
            # Retrieve relevant memory context
            memory_context = self.memory.get_context(chat_id, query) if chat_id else ""
            
            # In NORMAL mode: Simple direct response
            if not is_autonomous:
                response = await self._process_normal(query, memory_context)
            else:
                # In AUTONOMOUS mode: Full agent behavior
                response = await self._process_autonomous(query, memory_context, chat_id, user_id)
                tools_used = self._get_tools_used()
            
            # Calculate execution time
            execution_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Evaluate quality
            # Handle both string and AIResponse objects
            response_content = response.response.content if hasattr(response.response, 'content') else str(response.response)
            quality_score = await self.quality_judge.judge(
                response_content,
                ["helpful", "relevant", "accurate"],
                query
            )
            
            # Store interaction in memory
            if chat_id:
                self.memory.store_interaction(
                    chat_id, user_id, query, response.response,
                    response.model_used or "unknown",
                    self.scoring.analyze_intent(query).primary_intent
                )
            
            return AgentResponse(
                success=True,
                response=response_content,
                mode=mode.value,
                model_used=response.model_used,
                provider_used=response.provider_used,
                quality_score=quality_score,
                planning_active=is_autonomous,
                tools_used=tools_used,
                memory_used=bool(memory_context),
                execution_time_ms=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Agent processing error: {e}")
            return AgentResponse(
                success=False,
                response="An error occurred. Please try again.",
                mode=self.mode_manager.current_mode.value,
                error=str(e),
                execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
            )
    
    async def _process_normal(self, query: str, context: str) -> AICallResult:
        """Process in NORMAL mode - fast direct response."""
        # Build system prompt
        system_prompt = self._get_system_prompt()
        
        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        
        messages.append({"role": "user", "content": query})
        
        # Call provider chain
        result = await self.provider_chain.call(
            messages=messages,
            user_input=query,
            bypass_scoring=False
        )
        
        if result.success:
            result.response.content = self._format_response(result.response.content)
        
        return result
    
    async def _process_autonomous(self, query: str, context: str,
                                  chat_id: int, user_id: int) -> AICallResult:
        """Process in AUTONOMOUS mode - full agent behavior."""
        # Check for tool usage first (Tool-First Intelligence)
        tools_needed = self._detect_tool_needs(query)
        
        if tools_needed:
            # Use tools first
            tool_results = await self._execute_tools(tools_needed, query)
            context = f"{context}\n\nTool results:\n{tool_results}"
        
        # For now, use normal processing with enhanced context
        # The execution loop will be enhanced in future iterations
        result = await self._process_normal(query, context)
        result.model_used = f"[AUTONOMOUS] {result.model_used}"
        
        return result
    
    def _detect_tool_needs(self, query: str) -> List[str]:
        """Detect which tools are needed for the query."""
        tools = []
        query_lower = query.lower()
        
        # Web search detection
        search_keywords = ["search", "find", "latest", "news", "current", "recent", "what is", "who is", "where is"]
        if any(kw in query_lower for kw in search_keywords):
            tools.append("web_search")
        
        # Code execution detection
        code_keywords = ["calculate", "run", "execute", "compute", "python", "code"]
        if any(kw in query_lower for kw in code_keywords):
            tools.append("code_execution")
        
        # Memory recall detection
        recall_keywords = ["remember", "recall", "what did", "before", "previously", "past"]
        if any(kw in query_lower for kw in recall_keywords):
            tools.append("memory_recall")
        
        return tools
    
    async def _execute_tools(self, tools: List[str], query: str) -> str:
        """Execute required tools and return results."""
        results = []
        
        for tool_name in tools:
            try:
                params = {"query": query} if tool_name in ["web_search", "memory_recall"] else {}
                result = await self.tool_system.execute_tool(tool_name, params)
                
                if result.success:
                    results.append(f"[{tool_name}]: {result.data}")
                    self._record_tool_use(tool_name)
            except Exception as e:
                self.logger.warning(f"Tool {tool_name} failed: {e}")
        
        return "\n".join(results) if results else "No tool results"
    
    def _record_tool_use(self, tool_name: str):
        """Record tool usage for tracking."""
        # Store in agent state
        if not hasattr(self, '_tools_used'):
            self._tools_used = []
        self._tools_used.append(tool_name)
    
    def _get_tools_used(self) -> List[str]:
        """Get list of tools used in last execution."""
        return getattr(self, '_tools_used', [])
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for responses."""
        return """You are Genesis. 

**RESPONSE STYLE - CRITICAL:**
- NEVER say "I am an AI" or "As an AI assistant"
- NEVER introduce yourself
- Give DIRECT, CONCISE answers only
- No generic disclaimers
- Hinglish (Hindi+English mix) by default
- Skip introductions, jump straight to answering

Answer the user's question directly."""
    
    def _format_response(self, response: str) -> str:
        """Format response for output."""
        # Remove any remaining self-introductions
        lines = response.split('\n')
        cleaned_lines = []
        
        skip_next = False
        for line in lines:
            if skip_next:
                skip_next = False
                continue
            
            # Skip lines that are self-introductions
            if re.match(r'^(yes,?\s*i\s+can|I\s+am|of\s+course|I\'ll|hello|hi\s+there)', line.lower()):
                continue
            if re.match(r'^(I\'m\s+an|I\s+am\s+an|As\s+an)', line.lower()):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status and capabilities."""
        return {
            "mode": self.mode_manager.current_mode.value,
            "is_autonomous": self.mode_manager.is_autonomous(),
            "capabilities": self.mode_manager.get_capabilities(),
            "claude_available": self.scoring._claude_available,
            "available_providers": self.provider_chain.get_available_providers(),
            "request_log_size": len(self.provider_chain.get_request_log())
        }


# Singleton
_genesis_agent: Optional[GenesisAgent] = None


def get_genesis_agent() -> GenesisAgent:
    """Get or create Genesis Agent singleton."""
    global _genesis_agent
    if _genesis_agent is None:
        _genesis_agent = GenesisAgent()
    return _genesis_agent


# Convenience function
async def process_query(query: str, chat_id: int = 0, user_id: int = 0) -> AgentResponse:
    """Process query through Genesis Agent."""
    agent = get_genesis_agent()
    return await agent.process(query, chat_id, user_id)