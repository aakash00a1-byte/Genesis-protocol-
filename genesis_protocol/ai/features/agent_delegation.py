"""Genesis Protocol - Agent Delegation System

Spawn and manage specialized sub-agents for complex tasks.
Based on OpenHands sub-agent pattern.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("agent_delegation")


class AgentStatus(Enum):
    """Agent status codes."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubAgent:
    """A delegated sub-agent."""
    agent_id: str
    name: str
    role: str  # "coder", "researcher", "writer", "reviewer", etc.
    description: str
    instructions: str
    tools: List[str] = field(default_factory=list)
    model: str = "default"
    status: AgentStatus = AgentStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Any = None
    error: Optional[str] = None
    parent_id: Optional[str] = None


@dataclass
class DelegationTask:
    """A task delegated to a sub-agent."""
    task_id: str
    agent: SubAgent
    input_data: Dict[str, Any]
    result: Any = None
    status: AgentStatus = AgentStatus.PENDING


class AgentDelegationManager:
    """
    Manages sub-agent spawning and delegation.
    
    Features:
    - Spawn specialized sub-agents
    - Delegate tasks to agents
    - Aggregate results
    - Handle failures
    - Track agent lifecycle
    """
    
    # Predefined agent roles
    AGENT_ROLES = {
        "coder": {
            "name": "Coder Agent",
            "description": "Specializes in writing and editing code",
            "default_tools": ["file_editor", "terminal", "browser"]
        },
        "researcher": {
            "name": "Researcher Agent",
            "description": "Specializes in web search and information gathering",
            "default_tools": ["web_search", "browser", "memory"]
        },
        "writer": {
            "name": "Writer Agent",
            "description": "Specializes in creating documents and content",
            "default_tools": ["file_editor", "document"]
        },
        "reviewer": {
            "name": "Reviewer Agent",
            "description": "Specializes in code review and quality assurance",
            "default_tools": ["file_editor", "terminal"]
        },
        "tester": {
            "name": "Tester Agent",
            "description": "Specializes in writing and running tests",
            "default_tools": ["terminal", "file_editor"]
        },
        "debugger": {
            "name": "Debugger Agent",
            "description": "Specializes in finding and fixing bugs",
            "default_tools": ["terminal", "file_editor", "browser"]
        }
    }
    
    def __init__(self):
        """Initialize delegation manager."""
        self._agents: Dict[str, SubAgent] = {}
        self._tasks: Dict[str, DelegationTask] = {}
        self._agent_factory: Optional[Callable] = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        logger.info("AgentDelegationManager initialized")
    
    def set_agent_factory(self, factory: Callable):
        """
        Set the agent factory function.
        
        Args:
            factory: Function that creates agent instances
                      signature: (role, instructions, tools) -> agent
        """
        self._agent_factory = factory
        logger.debug("Agent factory set")
    
    def create_agent(self, role: str, instructions: str,
                    tools: List[str] = None,
                    model: str = "default",
                    name: str = None,
                    parent_id: str = None) -> SubAgent:
        """
        Create a new sub-agent.
        
        Args:
            role: Agent role (coder, researcher, etc.)
            instructions: Task instructions for the agent
            tools: Optional list of tools (defaults to role's tools)
            model: Optional model override
            name: Optional custom name
            parent_id: Parent agent ID for tracking
            
        Returns:
            Created SubAgent
        """
        agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        role_info = self.AGENT_ROLES.get(role, {})
        
        agent = SubAgent(
            agent_id=agent_id,
            name=name or role_info.get("name", f"{role.title()} Agent"),
            role=role,
            description=role_info.get("description", ""),
            instructions=instructions,
            tools=tools or role_info.get("default_tools", []),
            model=model,
            parent_id=parent_id
        )
        
        self._agents[agent_id] = agent
        logger.info(f"Created sub-agent: {agent_id} ({role})")
        
        return agent
    
    async def delegate_task(self, agent: SubAgent, 
                           input_data: Dict[str, Any]) -> DelegationTask:
        """
        Delegate a task to an agent.
        
        Args:
            agent: SubAgent to delegate to
            input_data: Input data for the task
            
        Returns:
            DelegationTask with result
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        
        task = DelegationTask(
            task_id=task_id,
            agent=agent,
            input_data=input_data,
            status=AgentStatus.RUNNING
        )
        
        agent.status = AgentStatus.RUNNING
        agent.started_at = datetime.utcnow()
        self._tasks[task_id] = task
        
        logger.info(f"Delegating task {task_id} to agent {agent.agent_id}")
        
        try:
            if self._agent_factory:
                # Use factory to create and run agent
                sub_agent = self._agent_factory(
                    role=agent.role,
                    instructions=agent.instructions,
                    tools=agent.tools
                )
                
                # Run the agent
                result = await sub_agent.run(input_data)
                task.result = result
                task.status = AgentStatus.COMPLETED
                agent.status = AgentStatus.COMPLETED
                agent.result = result
                
            else:
                # Simple execution (no LLM)
                # In real implementation, this would spawn an actual agent
                await asyncio.sleep(0.1)  # Simulate work
                task.result = {"status": "simulated", "message": "Agent factory not set"}
                task.status = AgentStatus.COMPLETED
                agent.status = AgentStatus.COMPLETED
            
            agent.completed_at = datetime.utcnow()
            logger.info(f"Task {task_id} completed by agent {agent.agent_id}")
            
        except Exception as e:
            task.status = AgentStatus.FAILED
            task.result = {"error": str(e)}
            agent.status = AgentStatus.FAILED
            agent.error = str(e)
            agent.completed_at = datetime.utcnow()
            logger.error(f"Task {task_id} failed: {e}")
        
        return task
    
    async def delegate_to_multiple(self, agents: List[SubAgent],
                                  inputs: List[Dict[str, Any]]) -> List[DelegationTask]:
        """
        Delegate tasks to multiple agents in parallel.
        
        Args:
            agents: List of SubAgents
            inputs: List of input data (one per agent)
            
        Returns:
            List of DelegationTask results
        """
        tasks = await asyncio.gather(*[
            self.delegate_task(agent, input_data)
            for agent, input_data in zip(agents, inputs)
        ], return_exceptions=True)
        
        return [t if not isinstance(t, Exception) else None for t in tasks]
    
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        """Get agent by ID."""
        return self._agents.get(agent_id)
    
    def get_task(self, task_id: str) -> Optional[DelegationTask]:
        """Get task by ID."""
        return self._tasks.get(task_id)
    
    def list_agents(self, status: AgentStatus = None) -> List[SubAgent]:
        """List all agents, optionally filtered by status."""
        agents = list(self._agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return agents
    
    def list_tasks(self, status: AgentStatus = None) -> List[DelegationTask]:
        """List all tasks, optionally filtered by status."""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks
    
    def cancel_agent(self, agent_id: str) -> bool:
        """Cancel a running agent."""
        agent = self._agents.get(agent_id)
        if agent and agent.status == AgentStatus.RUNNING:
            agent.status = AgentStatus.CANCELLED
            agent.completed_at = datetime.utcnow()
            logger.info(f"Cancelled agent: {agent_id}")
            return True
        return False
    
    def aggregate_results(self, task_ids: List[str]) -> Dict[str, Any]:
        """
        Aggregate results from multiple tasks.
        
        Args:
            task_ids: List of task IDs to aggregate
            
        Returns:
            Aggregated results dictionary
        """
        results = []
        errors = []
        
        for task_id in task_ids:
            task = self._tasks.get(task_id)
            if task:
                if task.status == AgentStatus.COMPLETED:
                    results.append(task.result)
                elif task.status == AgentStatus.FAILED:
                    errors.append({"task_id": task_id, "error": task.agent.error})
        
        return {
            "total_tasks": len(task_ids),
            "completed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
            "success_rate": len(results) / len(task_ids) if task_ids else 0
        }
    
    def cleanup_completed(self, older_than_hours: int = 24):
        """Remove completed/failed agents older than specified hours."""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        
        to_remove = []
        for agent_id, agent in self._agents.items():
            if agent.completed_at and agent.completed_at < cutoff:
                if agent.status in [AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.CANCELLED]:
                    to_remove.append(agent_id)
        
        for agent_id in to_remove:
            del self._agents[agent_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} completed agents")


# Singleton
_delegation_manager: Optional[AgentDelegationManager] = None


def get_delegation_manager() -> AgentDelegationManager:
    """Get global delegation manager."""
    global _delegation_manager
    if _delegation_manager is None:
        _delegation_manager = AgentDelegationManager()
    return _delegation_manager


# Quick delegation helper
async def quick_delegate(role: str, task: str, 
                        input_data: Dict[str, Any] = None,
                        manager: AgentDelegationManager = None) -> Any:
    """
    Quick helper to delegate a single task.
    
    Args:
        role: Agent role
        task: Task description
        input_data: Optional input data
        manager: Optional delegation manager
        
    Returns:
        Task result
    """
    if manager is None:
        manager = get_delegation_manager()
    
    agent = manager.create_agent(role, task)
    delegation_task = await manager.delegate_task(agent, input_data or {})
    
    return delegation_task.result
