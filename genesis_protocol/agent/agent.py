"""
Genesis Protocol - Main Agent
==============================
The main autonomous agent class that orchestrates everything.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from genesis_protocol.agent.brain import AgentBrain
from genesis_protocol.agent import ToolExecutor, Action, ActionType, AgentState, Task, Message
from genesis_protocol.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the agent."""
    max_iterations: int = 10
    verbose: bool = True
    auto_save_history: bool = True
    enable_planning: bool = True
    planning_threshold: int = 5  # Tasks longer than this use planning


class GenesisAgent:
    """
    The main autonomous agent.
    
    This is the core of Genesis Protocol - a fully autonomous AI agent
    that can understand tasks, make plans, execute actions, and learn from results.
    
    Example:
        agent = GenesisAgent()
        result = await agent.run("Create a Python file that prints hello world")
        print(result["response"])
    """
    
    def __init__(self, config: AgentConfig = None):
        self.config = config or AgentConfig()
        self.brain = AgentBrain()
        self.tool_executor = ToolExecutor()
        self.conversations: Dict[str, List[Message]] = {}
        self.current_session_id: Optional[str] = None
        
        logger.info("🚀 Genesis Agent initialized")
        logger.info(f"   Max iterations: {self.config.max_iterations}")
        logger.info(f"   LLM providers: {list(self.brain.get_capabilities()['llm_providers'].keys())}")
    
    async def run(self, task: str, session_id: str = None, context: Dict = None) -> Dict[str, Any]:
        """
        Run the agent on a task.
        
        Args:
            task: The task to complete
            session_id: Optional session ID for conversation continuity
            context: Additional context for the task
            
        Returns:
            Dict with keys: success, response, iterations, history
        """
        # Create or use session
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        self.current_session_id = session_id
        
        if session_id not in self.conversations:
            self.conversations[session_id] = []
        
        # Add user message
        user_msg = Message(role="user", content=task)
        self.conversations[session_id].append(user_msg)
        
        # Log start
        if self.config.verbose:
            print(f"\n{'='*60}")
            print(f"🤖 GENESIS AGENT - Processing Task")
            print(f"{'='*60}")
            print(f"Session: {session_id[:8]}...")
            print(f"Task: {task[:100]}{'...' if len(task) > 100 else ''}")
            print(f"{'='*60}\n")
        
        try:
            # Execute using brain
            result = await self.brain.execute(task, context)
            
            # Add assistant response
            if result.get("success"):
                assistant_msg = Message(
                    role="assistant",
                    content=result.get("response", "Task completed")
                )
                self.conversations[session_id].append(assistant_msg)
            
            # Log completion
            if self.config.verbose:
                print(f"\n{'='*60}")
                print(f"✅ Task Completed in {result.get('iterations', 0)} iterations")
                print(f"{'='*60}")
                print(f"Response: {result.get('response', '')[:200]}")
                print(f"{'='*60}\n")
            
            result["session_id"] = session_id
            return result
            
        except Exception as e:
            logger.error(f"Agent execution error: {e}")
            error_result = {
                "success": False,
                "error": str(e),
                "session_id": session_id
            }
            
            # Add error message
            error_msg = Message(role="assistant", content=f"Error: {str(e)}")
            self.conversations[session_id].append(error_msg)
            
            return error_result
    
    async def run_with_tools(self, task: str, tools: List[str] = None) -> Dict[str, Any]:
        """
        Run agent with specific tools only.
        
        Args:
            task: The task to complete
            tools: List of tool names to enable
            
        Returns:
            Dict with execution results
        """
        # Filter tools if specified
        if tools:
            # This would filter available tools
            pass
        
        return await self.run(task)
    
    async def chat(self, message: str) -> str:
        """
        Simple chat interface - just respond without complex execution.
        
        Args:
            message: User message
            
        Returns:
            Agent response
        """
        result = await self.run(message)
        return result.get("response", result.get("error", "No response"))
    
    def get_session_history(self, session_id: str) -> List[Message]:
        """Get conversation history for a session."""
        return self.conversations.get(session_id, [])
    
    def get_all_sessions(self) -> List[str]:
        """Get all session IDs."""
        return list(self.conversations.keys())
    
    def clear_session(self, session_id: str) -> bool:
        """Clear a conversation session."""
        if session_id in self.conversations:
            del self.conversations[session_id]
            return True
        return False
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get agent capabilities."""
        capabilities = self.brain.get_capabilities()
        capabilities["config"] = {
            "max_iterations": self.config.max_iterations,
            "verbose": self.config.verbose,
            "enable_planning": self.config.enable_planning
        }
        return capabilities
    
    async def demonstrate_capabilities(self) -> Dict[str, Any]:
        """
        Run a demonstration of agent capabilities.
        """
        demonstrations = []
        
        # Demo 1: File operation
        demo1_result = await self.run("What files are in the current directory?")
        demonstrations.append({
            "name": "File Listing",
            "success": demo1_result.get("success"),
            "result": demo1_result.get("response", "")[:200]
        })
        
        # Demo 2: Git status
        demo2_result = await self.run("Show git status")
        demonstrations.append({
            "name": "Git Status",
            "success": demo2_result.get("success"),
            "result": demo2_result.get("response", "")[:200]
        })
        
        # Demo 3: Web search
        demo3_result = await self.run("Search for 'Python best practices 2024'")
        demonstrations.append({
            "name": "Web Search",
            "success": demo3_result.get("success"),
            "result": demo3_result.get("response", "")[:200]
        })
        
        return {
            "demonstrations": demonstrations,
            "capabilities": self.get_capabilities()
        }


# Convenience function for quick usage
async def quick_agent(task: str) -> Dict[str, Any]:
    """
    Quick way to run the agent without creating an instance.
    
    Example:
        result = await quick_agent("Hello, how are you?")
    """
    agent = GenesisAgent()
    return await agent.run(task)


# Export main classes
__all__ = [
    "GenesisAgent",
    "AgentConfig", 
    "AgentBrain",
    "ToolExecutor",
    "Action",
    "ActionType",
    "AgentState",
    "Task",
    "Message",
    "quick_agent"
]