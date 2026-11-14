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
import json
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
from genesis_protocol.ai.failure_communicator import FailureCommunicator, get_failure_communicator, FailureType
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
        
        # Labelled search results from the current request, kept so the answer
        # can be followed by a deterministic sources list the model cannot alter.
        self._last_search_results = []

        # Update Claude availability
        self._update_claude_status()
        
        logger.info("Genesis Agent v2 initialized")
    
    def _empty_response_failure(self):
        """Classify an empty provider response.

        An empty result with no provider configured is a deployment gap, not a
        bad question, so the two cases get different wording. Telling a user to
        rephrase when no key exists would be misleading.
        """
        try:
            available = self.provider_chain.get_available_providers()
        except Exception:
            available = []
        if not available:
            return (
                FailureType.NO_PROVIDERS,
                "No provider API key is configured",
            )
        return (
            FailureType.PROVIDER_EMPTY,
            "Provider returned empty or invalid response",
        )

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
        except Exception:
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
        self._last_search_results = []
        
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
            # Add durable, user-approved cross-session memory (agentic store).
            memory_context = self._with_durable_memory(user_id, query, memory_context)
            
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
                # Use failure communicator instead of generic "Sorry..."
                fc = get_failure_communicator()
                failure_type, reason = self._empty_response_failure()
                response_content = fc.communicate(
                    failure_type=failure_type,
                    reason=reason,
                    attempts=["primary_provider"],
                    query=query
                )
            
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
            
            # Append the deterministic sources list for live-info answers.
            response_content = response_content + self._sources_footer()

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
                    # Still no response - use failure communicator
                    fc = get_failure_communicator()
                    failure_type, reason = self._empty_response_failure()
                    fallback_message = fc.communicate(
                        failure_type=failure_type,
                        reason=reason,
                        attempts=["primary_provider", "fallback_provider"],
                        query=query
                    )
                    result.response.content = fallback_message
                    self.logger.warning("Provider returned empty content, using failure communicator")
        
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
                tool_results, failures = await self._execute_tools(
                    tools_needed, query, user_id
                )
                context = f"{context}\n\nTool results:\n{tool_results}"
                if failures:
                    context += (
                        "\n\nTool failure warning: the following tools were needed "
                        "but did NOT return usable data: " + "; ".join(failures) + ". "
                        "Do NOT invent news, weather, prices, dates, URLs or any "
                        "other live fact to fill the gap. State plainly that the "
                        "live lookup failed and that you cannot confirm current "
                        "information without it."
                    )
            
            # Use normal processing with enhanced context
            result = await self._process_normal(query, context)
            result.model_used = f"[AUTONOMOUS] {result.model_used}"
            
            return result
        except Exception as e:
            self.logger.error(f"Autonomous processing failed: {e}")
            # Use failure communicator for graceful fallback
            fc = get_failure_communicator()
            fc.communicate(
                failure_type=FailureType.AUTONOMOUS_FAILED,
                reason=str(e),
                attempts=["autonomous_mode"],
                query=query
            )
            # Fallback to normal mode
            return await self._process_normal(query, context)
    
    def _with_durable_memory(self, user_id: int, query: str, base_context: str) -> str:
        """Append durable, user-approved memory to the chat context.

        Only approved facts from this user's own store are eligible, so recall
        is cross-session but never cross-user. Any failure here is swallowed:
        memory is an enhancement, and must not break chat.
        """
        if not user_id:
            return base_context
        try:
            from genesis_protocol.agentic.memory import get_agent_memory

            recalled = get_agent_memory().recall(user_id, query, limit=5)
        except Exception:
            return base_context
        if not recalled:
            return base_context
        lines = "\n".join(f"- {m['content'][:200]}" for m in recalled)
        block = f"Known facts about this user (approved memory):\n{lines}"
        return f"{base_context}\n\n{block}" if base_context else block

    def _detect_tool_needs(self, query: str) -> List[str]:
        """Detect which tools are needed for the query."""
        tools = []
        query_lower = query.lower()
        
        # CRITICAL: ALWAYS get real-time data for these topics
        realtime_keywords = [
            # Date/Time
            "date", "time", "din", "taarikh", "samay", "aj", "aaj", "kal", "pars",
            "today", "tomorrow", "yesterday", "day", "month", "year",
            # Weather
            "weather", "mausam", "baarish", "garmi", "sardi", "temprature", 
            "thand", "dhoom", "sunny", "rainy", "cloudy",
            # Current events
            "news", "khabar", "latest", "current", "recent", "abhi", "right now",
            # Search queries
            "search", "find", "what is", "who is", "where is", "how is",
            "kya hai", "kaun sa", "kitna", "kaisa",
        ]
        
        # Weather and currency have exact, key-free providers, so they do not
        # need a search. Snippets rarely carry the number anyway.
        weather_keywords = ["weather", "mausam", "baarish", "garmi", "sardi",
                            "temperature", "temprature", "forecast", "thand",
                            "sunny", "rainy", "cloudy"]
        fx_keywords = ["exchange rate", "usd", "inr", "eur", "gbp", "rupee",
                       "dollar", "euro", "pound", "currency", "conversion rate"]

        is_weather = any(kw in query_lower for kw in weather_keywords)
        is_fx = any(kw in query_lower for kw in fx_keywords) and (
            "rate" in query_lower or "convert" in query_lower
            or "currency" in query_lower or "usd" in query_lower
        )

        if is_weather:
            tools.append("get_weather")
        if is_fx:
            tools.append("get_exchange_rate")

        # Arithmetic needs no lookup; compute it before the search check so it
        # can suppress a lookup ("what is 2+2" matched "what is").
        expression = self._math_expression(query)

        if (any(kw in query_lower for kw in realtime_keywords)
                and not is_weather and not is_fx and not expression):
            tools.append("web_search")
        
        # Plain arithmetic goes to the safe calculator, not to code execution.
        # "calculate 17*23" used to route to the restricted code_execution tool,
        # so a non-owner got a denial and the model answered from memory - the
        # live probe returned 437 for 17*23. The calculator is whitelist-based
        # (see tools.safe_math) and needs no code execution at all.
        if expression:
            tools.append("calculator")

        # Code execution only for a fenced code block, which the calculator
        # cannot evaluate. Broad "run/execute/code" wording is common in
        # ordinary questions and used to trigger a call that could only fail.
        if self._extract_code_block(query):
            tools.append("code_execution")
        
        # Memory: an explicit "remember X" is a store; a question about the
        # past is a recall. Treating both as recall meant a stored fact was
        # never written.
        store_markers = ["remember that", "remember:", "remember this",
                         "note that", "save this", "yaad rakho", "yaad rakhna"]
        recall_markers = ["do you remember", "what did i", "recall", "previously",
                          "yaad hai", "pichla"]
        if any(m in query_lower for m in store_markers):
            tools.append("memory_store")
        elif any(m in query_lower for m in recall_markers):
            tools.append("memory_recall")
        
        # Notes and tasks: the user's own saved notes and task list. The action
        # (save/list/create/complete) is chosen in _build_tool_params, which
        # sees the same query.
        notes_markers = ["save note", "make a note", "take a note", "add a note",
                         "note down", "note this", "note le lo", "note likh",
                         "my notes", "list notes", "show notes", "mere notes",
                         "notes dikhao", "saved notes"]
        if any(m in query_lower for m in notes_markers):
            tools.append("notes")

        task_markers = ["add task", "create task", "new task", "add a task",
                        "task add", "task banao", "kaam add",
                        "my tasks", "list tasks", "show tasks", "mere tasks",
                        "task list", "kaam dikhao"]
        if any(m in query_lower for m in task_markers):
            tools.append("task_manager")

        return tools
    
    def _tool_policy(self):
        """The policy used to authorize chat tool calls (lazy import)."""
        try:
            from genesis_protocol.agentic.policy import get_agent_policy

            return get_agent_policy()
        except Exception:
            return None

    def _authorize_chat_tool(self, policy, tool_name: str, user_id: int):
        """Authorize one chat tool call by its registry permission level.

        The chat path used to run every detected tool with no policy check, so
        a non-owner could reach restricted tools (code_execution, file_reader)
        that the policy layer intends to reserve for the owner. The permission
        is read from the canonical registry; a tool that is not there is left
        to the tool system (returns ``None`` meaning "no opinion").
        """
        if policy is None:
            return None
        # Chat tool names that are not canonical registry entries, mapped to the
        # permission level their implementation carries.
        chat_only_permissions = {
            "code_execution": "restricted",
            "file_reader": "restricted",
            "get_weather": "safe",
            "get_exchange_rate": "safe",
        }
        try:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            tool = get_tool_registry().get_tool(tool_name)
            if tool is not None:
                perm = getattr(getattr(tool, "permission", None), "value", None)
            else:
                perm = chat_only_permissions.get(tool_name)
            if perm is None:
                return None
            # A chat request from the owner is the owner's own instruction, so
            # it counts as approval for restricted tools. Non-owners are still
            # refused; they can never approve their own restricted call.
            return policy.authorize_tool(
                user_id, tool_name, permission=perm,
                owner_approved=policy.is_owner(user_id),
            )
        except Exception:
            return None

    async def _execute_tools(self, tools: List[str], query: str,
                             user_id: int = 0) -> tuple:
        """Execute required tools.

        Returns ``(results_text, failures)``. ``failures`` lists tools that were
        needed but returned nothing usable, so the caller can tell the model not
        to invent an answer. Previously a failed or mis-read tool produced
        "No tool results" and the model filled the gap with fabricated news,
        weather and prices.
        """
        results = []
        failures = []
        self._last_search_results = []

        policy = self._tool_policy()

        for tool_name in tools:
            try:
                decision = self._authorize_chat_tool(policy, tool_name, user_id)
                if decision is not None and not decision.allowed:
                    # A restricted tool the caller may not run is reported as a
                    # failure, not silently skipped: the model is then told not
                    # to invent a result for it.
                    failures.append(f"{tool_name}: {decision.reason}")
                    continue

                params = self._build_tool_params(tool_name, query, user_id)
                result = await self.tool_system.execute_tool(tool_name, params)

                # ToolResult carries ``data`` (and ``error``); it has no
                # ``response`` attribute. Reading ``result.response`` raised
                # AttributeError, which the except below swallowed, so a
                # successful search was silently discarded.
                if result.success and result.data:
                    results.append(f"[{tool_name}]:\n{self._format_tool_data(tool_name, result.data)}")
                    if tool_name == "web_search" and isinstance(result.data, dict):
                        self._last_search_results = result.data.get("results", [])
                    self._record_tool_use(tool_name)
                else:
                    failures.append(f"{tool_name}: {result.error or 'no data returned'}")
            except Exception as e:
                self.logger.warning(f"Tool {tool_name} failed: {e}")
                failures.append(f"{tool_name}: {e}")

        return ("\n".join(results) if results else "No tool results"), failures

    # Common words that are never a place or currency name.
    _STOPWORDS = {
        "what", "whats", "is", "the", "in", "of", "at", "for", "today",
        "now", "current", "currently", "ka", "ki", "ke", "mein", "me", "hai",
        "weather", "temperature", "forecast", "aaj", "abhi", "rate",
        "exchange", "currency", "convert", "conversion", "please", "tell",
        "and", "to", "from", "how", "much", "does", "do",
        "mausam", "kaisa", "kaisi", "kaise", "kya", "bata", "batao", "kitna",
        "kitni", "hain", "h", "hai", "degree", "degrees", "celsius",
        "fahrenheit", "sunny", "rainy", "cloudy", "forecast",
    }

    @staticmethod
    def _math_expression(query: str) -> str:
        """The plain arithmetic in a query, or "" (shared with mode switching)."""
        from genesis_protocol.ai.autonomous_mode import extract_math_expression

        return extract_math_expression(query)

    @staticmethod
    def _extract_code_block(query: str) -> str:
        """The body of a fenced code block, or "" (an empty fence is not code)."""
        fenced = re.search(r"```(?:python|py)?\s*\n?(.*?)```", query, re.S)
        return fenced.group(1).strip() if fenced else ""

    @staticmethod
    def _extract_code(query: str) -> str:
        """Pull runnable Python out of a query, or return "".

        The tool-first path runs before the model sees the question, so the
        model never gets a chance to write the code the tool is meant to run.
        We therefore only invoke code execution when the query itself carries
        runnable code (a fenced block or a plain arithmetic expression). Any
        other "run/execute" wording is left to the model to answer, rather than
        firing a tool call that can only fail with "No code provided".
        """
        fenced = re.search(r"```(?:python|py)?\s*\n?(.*?)```", query, re.S)
        if fenced and fenced.group(1).strip():
            return fenced.group(1).strip()

        expr = re.search(
            r"(?:calculate|compute|evaluate|what\s+is)\s*"
            r"([0-9][0-9\.\s\+\-*/%()\^]*[0-9\)])",
            query, re.I,
        )
        if expr:
            candidate = expr.group(1).strip().rstrip("+-*/^%")
            if candidate and re.fullmatch(r"[0-9\.\s\+\-*/%()\^]+", candidate):
                return f"print({candidate.replace('^', '**')})"
        return ""

    def _build_tool_params(self, tool_name: str, query: str,
                           user_id: int = 0) -> Dict:
        """Extract the parameters each tool needs from a free-text query."""
        if tool_name == "web_search":
            return {"query": query}

        if tool_name == "get_weather":
            words = [w for w in re.findall(r"[A-Za-z]+", query)
                     if w.lower() not in self._STOPWORDS]
            return {"location": " ".join(words).strip() or query.strip()}

        if tool_name == "code_execution":
            return {"code": self._extract_code(query)}

        if tool_name == "memory_recall":
            return {"query": query, "user_id": user_id}

        if tool_name == "memory_store":
            text = query.strip()
            for lead in ("remember that", "remember:", "remember", "note that",
                         "yaad rakho ki", "yaad rakho", "yaad rakhna"):
                if text.lower().startswith(lead):
                    text = text[len(lead):].lstrip(" :,-")
                    break
            return {"key": text[:60] or "fact", "value": text, "user_id": user_id}

        if tool_name == "calculator":
            return {"expression": self._math_expression(query)}

        if tool_name == "notes":
            lower = query.lower()
            store_markers = ["save note", "make a note", "take a note", "add a note",
                             "note down", "note this", "note le lo", "note likh"]
            if any(m in lower for m in store_markers):
                text = query
                for lead in ("save note", "make a note", "take a note", "add a note",
                             "note down", "note this", "note le lo", "note likh"):
                    pos = lower.find(lead)
                    if pos != -1:
                        text = query[pos + len(lead):].lstrip(" :,-")
                        break
                return {"action": "save", "key": (text[:60] or "note"),
                        "content": text, "user_id": user_id}
            return {"action": "list", "user_id": user_id}

        if tool_name == "task_manager":
            lower = query.lower()
            create_markers = ["add task", "create task", "new task", "add a task",
                              "task add", "task banao", "kaam add"]
            if any(m in lower for m in create_markers):
                text = query
                for lead in ("add task", "create task", "new task", "add a task",
                             "task add", "task banao", "kaam add"):
                    pos = lower.find(lead)
                    if pos != -1:
                        text = query[pos + len(lead):].lstrip(" :,-")
                        break
                return {"action": "create", "name": text[:120] or "task",
                        "user_id": user_id}
            return {"action": "list", "user_id": user_id}


        if tool_name == "get_exchange_rate":
            codes = re.findall(r"\b[A-Z]{3}\b", query.upper())
            # Fall back to well-known currency words when no ISO code is present.
            names = {"dollar": "USD", "rupee": "INR", "euro": "EUR",
                     "pound": "GBP", "yen": "JPY"}
            for word, code in names.items():
                if word in query.lower() and code not in codes:
                    codes.append(code)
            base = codes[0] if codes else "USD"
            quote = next((c for c in codes[1:] if c != base), "INR")
            return {"base": base, "quote": quote}

        return {}

    def _format_tool_data(self, tool_name: str, data) -> str:
        """Render tool data as text the model can cite without guessing."""
        if tool_name == "web_search" and isinstance(data, dict):
            from genesis_protocol.integrations.source_credibility import (
                format_for_model, group_by_label, overall,
            )
            results = data.get("results", [])
            counts = {k: len(v) for k, v in group_by_label(results).items()}
            fresh = sum(1 for r in results if r.get("bucket") == "fresh")
            header = (
                f"overall confidence: {overall(results)} | "
                f"verified: {counts['verified']}, "
                f"developing: {counts['developing']}, "
                f"promotional: {counts['promotional-unverified']} | "
                f"published in last 24h: {fresh}"
            )
            body = format_for_model(results)
            answer = data.get("answer")
            if answer:
                body += f"\n- [summary] {answer}"
            return f"{header}\n{body}"

        if tool_name == "code_execution" and isinstance(data, dict):
            out = (data.get("output") or "").strip()
            err = (data.get("error") or "").strip()
            parts = []
            if out:
                parts.append(f"stdout:\n{out}")
            if err:
                parts.append(f"stderr:\n{err}")
            return "\n".join(parts) or "(no output)"

        if tool_name == "calculator" and isinstance(data, dict):
            if "result" in data:
                return f"{data.get('expression', '')} = {data['result']}"
            return str(data)

        if tool_name == "notes" and isinstance(data, dict):
            if "notes" in data:
                items = data.get("notes") or []
                return "no saved notes" if not items else "\n".join(f"- {n}" for n in items)
            return data.get("message") or "(note handled)"

        if tool_name == "task_manager" and isinstance(data, dict):
            if "tasks" in data:
                items = data.get("tasks") or []
                if not items:
                    return "no tasks"
                return "\n".join(
                    f"- [{t.get('status')}] {t.get('name')} (id {t.get('id')})" for t in items
                )
            return data.get("message") or "(task handled)"


        if tool_name in ("memory_store", "memory_recall") and isinstance(data, dict):
            if data.get("stored"):
                return f"stored key: {data.get('key')}"
            if "results" in data:
                items = data.get("results") or []
                if not items:
                    return "no matching memories"
                return "\n".join(f"- {m.get('value') or m.get('content')}" for m in items)

        return json.dumps(data, ensure_ascii=False, default=str)

    def _sources_footer(self) -> str:
        """Build a sources list from the labelled results, independent of the model.

        The model is asked to cite sources, but a model can move an item under a
        stronger heading or drop the tag. This footer is generated from the tool
        data itself, so the label, source, age and link shown to the user are
        the ones the tool produced, not the ones the model chose to repeat.
        """
        if not self._last_search_results:
            return ""
        try:
            from genesis_protocol.integrations.source_credibility import group_by_label

            groups = group_by_label(self._last_search_results)
        except Exception:
            return ""

        order = [
            ("verified", "Verified"),
            ("developing", "Developing"),
            ("promotional-unverified", "Promotional / Unverified"),
        ]
        lines = []
        for key, title in order:
            items = groups.get(key) or []
            if not items:
                continue
            lines.append(f"**{title}**")
            for r in items[:5]:
                source = r.get("publisher") or r.get("domain") or "unknown"
                age = r.get("age") or "unknown"
                lines.append(
                    f"- {r.get('title', '').strip()} - {source} "
                    f"({age}) {r.get('url') or 'no link'}"
                )
        if not lines:
            return ""
        return "\n\n---\n**Sources (labels and links come from the search tool)**\n" + "\n".join(lines)

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
        """Get system prompt for responses with live info."""
        
        # Get live info
        info = None
        try:
            from genesis_protocol.integrations import get_live_info_service
            service = get_live_info_service()
            info = service.get_all_info()
            live_time = f"{info.date} {info.time}" if info.date else "Unknown"
            live_weather = f"{info.weather.icon} {info.weather.temp}°C, {info.weather.condition}" if info.weather else "Unknown"
            live_location = f"{info.location.city}, {info.location.region}" if info.location else "Unknown"
            news_headline = info.news[0]['title'] if info.news and len(info.news) > 0 else "No recent news"
        except Exception:
            live_time = "Unknown"
            live_weather = "Unknown"
            live_location = "Unknown"
            news_headline = "Unknown"
        
        return f"""**IMPORTANT - REAL-TIME DATA RULES:**
- TODAY IS: {info.date if info and info.date else "Unknown"}
- CURRENT TIME: {live_time}
- Do NOT guess the date - use the date provided above
- If user asks about weather, news, or current events - USE WEB SEARCH
- Your training data is OLD - always verify with live tools for current info
- NEVER say "according to my knowledge" or "as of my last update"

**HONESTY RULE - NON-NEGOTIABLE:**
- NEVER invent live facts: news headlines, weather, prices, exchange rates,
  dates, URLs, scores or any current event. Not even as an example.
- If the context above contains a "Tool failure warning", the live lookup did
  NOT succeed. Say so plainly and stop. Do NOT narrate a fake action such as
  "*searching...*" or "*Google search karke dekhta hoon*" and then present a
  made-up result. A fabricated answer is worse than admitting the tool failed.
- Only state a live fact if it appears in the tool results above. Otherwise say
  the lookup failed and that you cannot confirm current information.

**CITATION & SOURCE-QUALITY RULES - CRITICAL:**
- When you report a news item, include its real source link from the tool
  results. Never substitute a generic homepage for the article URL, and never
  invent a URL.
- Copy the credibility label that the tool gives each item and explain it in
  plain words:
  - verified -> "verified: reported by <source>"
  - developing -> "developing: only <source> is reporting this so far"
  - promotional-unverified -> "promotional/unverified: this is a press release
    or self-reported claim, not independent reporting"
- Never present a promotional or single-source item as confirmed fact. Say
  plainly how strong the evidence is. If the overall confidence is not
  verified, say so before the headlines.
- Present news grouped into the same three sections the tool returns, in this
  order: "Verified", "Developing", and "Promotional / Unverified". Keep every
  item inside its own section; do not mix a press release in with verified
  reporting. If a section is empty, omit it.
- Mention how old each item is when the tool gives a "published" age. Do not
  present an item older than a day as if it were today's news.
- Every item in the tool output carries a tag such as [VERIFIED], [DEVELOPING]
  or [PROMOTIONAL-UNVERIFIED]. Keep that tag with the item. Never move an item
  under a stronger heading than its tag, and never drop the tag.

**RESPONSE STYLE - CRITICAL:**
- Give DIRECT, CONCISE answers only
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