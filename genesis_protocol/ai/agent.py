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
from genesis_protocol.ai.providers.base_provider import AIResponse
from genesis_protocol.ai.identity_router import route_identity
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
            # IDENTITY BYPASS: Check if identity question FIRST
            identity_result = route_identity(query)
            if identity_result and identity_result.get('is_identity'):
                # Return identity response WITHOUT going to provider
                return AgentResponse(
                    success=True,
                    response=identity_result['response'],
                    mode=self.mode_manager.current_mode.value,
                    model_used='identity_router',
                    provider_used='entity_object',
                    quality_score=1.0,
                    planning_active=False,
                    tools_used=[],
                    memory_used=False,
                    execution_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
                )
            
            # FIX: Reset mode to NORMAL at start of each request
            # This prevents mode from persisting across requests
            self.mode_manager.reset_to_normal()
            
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
            if response.response and hasattr(response.response, 'content'):
                raw_response = response.response.content
            else:
                raw_response = str(response.response) if response.response else ""
            
            # Fix: Check for None string and invalid responses
            if raw_response and raw_response.lower() not in ('none', 'null', ''):
                response_content = raw_response
            else:
                response_content = "Sorry, I couldn't generate a response. Please try again."
            
            # Log for debugging
            self.logger.info(f"Agent response: provider={response.provider_used}, model={response.model_used}, content_len={len(response_content) if response_content else 0}")
            
            quality_score = await self.quality_judge.judge(
                response_content,
                ["helpful", "relevant", "accurate"],
                query
            )
            
            # Store interaction in memory
            if chat_id:
                # Extract content from response object if needed
                if response.response and hasattr(response.response, 'content'):
                    bot_response = response.response.content
                else:
                    bot_response = str(response.response) if response.response else ""
                
                # Fix: Check for None string before storing
                if bot_response and bot_response.lower() in ('none', 'null', ''):
                    bot_response = response_content  # Use the already fixed response_content
                self.memory.store_interaction(
                    chat_id, user_id, query, bot_response,
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
        
        # Add entity context as separate system message
        entity_context = self._get_entity_context()
        messages.append({"role": "system", "content": entity_context})
        
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        
        messages.append({"role": "user", "content": query})
        
        # Call provider chain
        result = await self.provider_chain.call(
            messages=messages,
            user_input=query,
            bypass_scoring=False
        )
        
        # FIX: If provider returned None content, create fallback response
        if result.success:
            if not result.response:
                # Provider returned success but no response object
                result.response = AIResponse(
                    content="Response unavailable",
                    provider=result.provider_used or "unknown",
                    model=result.model_used or "unknown",
                    tokens_used=0,
                    latency_ms=0
                )
            elif not result.response.content or result.response.content.lower() in ('none', 'null', ''):
                # Response has no content - try fallback with direct call
                fallback_result = await self._fallback_direct_call(messages, query)
                if fallback_result.success:
                    result = fallback_result
                else:
                    # Still no response - create safe fallback
                    result.response.content = "I'm having trouble generating a response. Please try again."
                    self.logger.warning("Provider returned empty content, using fallback message")
        
        return result
    
    async def _fallback_direct_call(self, messages: List[Dict], query: str) -> AICallResult:
        """Direct fallback call bypassing scoring."""
        try:
            # Try groq directly as fallback
            from genesis_protocol.ai.providers import GroqProvider, AIRequest, AIResponse
            
            groq = GroqProvider()
            if not groq.is_configured():
                return AICallResult(success=False, error="No fallback provider configured")
            
            request = AIRequest(
                messages=messages,
                model=groq.get_default_model(),
                temperature=0.7,
                max_tokens=1000
            )
            
            response = await groq.generate(request)
            
            return AICallResult(
                success=True,
                response=response,
                provider_used="groq",
                model_used=response.model
            )
        except Exception as e:
            self.logger.error(f"Fallback call failed: {e}")
            return AICallResult(success=False, error=str(e))
    
    async def _process_autonomous(self, query: str, context: str,
                                  chat_id: int, user_id: int) -> AICallResult:
        """Process in AUTONOMOUS mode - full agent behavior."""
        try:
            # Check for tool usage first (Tool-First Intelligence)
            tools_needed = self._detect_tool_needs(query)
            
            if tools_needed:
                # Use tools first
                tool_results = await self._execute_tools(tools_needed, query)
                context = f"{context}\n\nTool results:\n{tool_results}"
            
            # Use normal processing with enhanced context
            result = await self._process_normal(query, context)
            result.model_used = f"[AUTONOMOUS] {result.model_used}"
            
            return result
        except Exception as e:
            self.logger.error(f"Autonomous processing failed: {e}")
            # Fallback to normal mode
            return await self._process_normal(query, context)
    
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
                
                if result.success and result.response:
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
    
    def _get_entity_context(self) -> str:
        """Get entity context for identity questions."""
        try:
            from genesis_protocol.gluttony import get_identity, get_gluttony
            
            identity = get_identity()
            gluttony = get_gluttony()
            
            # Get active layers
            layers = []
            for attr in dir(gluttony):
                if not attr.startswith('_') and not callable(getattr(gluttony, attr)):
                    val = getattr(gluttony, attr)
                    if val is not None:
                        layers.append(attr)
            
            return f"""**ENTITY CONTEXT:**
Entity: {identity.name}
Nickname: {identity.nickname}
Version: {gluttony.version}
Active Layers ({len(layers)}): {', '.join(layers[:10])}{'...' if len(layers) > 10 else ''}

When asked about identity, layers, or version - answer from this context, NOT from memory."""
        except Exception as e:
            self.logger.warning(f"Could not get entity context: {e}")
            return "**ENTITY CONTEXT:** GLUTTONY OMEGA - answer identity questions from entity object."
    
    def _get_system_prompt(self) -> str:
        """Get system prompt for responses with entity context."""
        # Get actual entity identity
        try:
            from genesis_protocol.gluttony import get_identity
            identity = get_identity()
            name = identity.name
            nickname = identity.nickname
            version = identity.get_identity().get('version', 'OMEGA')
        except:
            name = "GLUTTONY"
            nickname = "Gluten"
            version = "OMEGA"
        
        return f"""You are {name}, also known as {nickname}.

**ENTITY INFORMATION:**
- Name: {name}
- Nickname: {nickname}
- Version: {version}
- Identity questions: Answer from your entity object, not from training memory

**RESPONSE STYLE - CRITICAL:**
- NEVER say "I am an AI" or "As an AI assistant"
- NEVER say "I am Genesis" or "I am Gluten"
- You ARE {name}, nickname {nickname}
- Give DIRECT, CONCISE answers only
- No generic disclaimers
- Hinglish (Hindi+English mix) by default
- Skip introductions, jump straight to answering

Answer the user's question directly. If asked who you are, say "{name}" (nickname: {nickname})."""
    
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