"""Genesis Protocol - Parallel Tool Executor

Execute multiple independent tools simultaneously for speed improvement.
Based on OpenHands parallel tool execution pattern.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger("ai.parallel_executor")


class ToolStatus(Enum):
    """Tool execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolTask:
    """A tool execution task."""
    id: str
    name: str
    arguments: Dict[str, Any]
    status: ToolStatus = ToolStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    execution_time_ms: int = 0


@dataclass
class ParallelResult:
    """Result of parallel execution."""
    tasks: List[ToolTask]
    total_time_ms: int
    success_count: int
    failed_count: int
    cancelled_count: int


class ParallelToolExecutor:
    """
    Execute multiple independent tools in parallel.
    
    Benefits:
    - Faster execution for independent tasks
    - Better resource utilization
    - Reduced total latency
    
    Usage:
        executor = ParallelToolExecutor()
        executor.add_task("web_search", {"query": "AI news"})
        executor.add_task("web_search", {"query": "Python trends"})
        results = await executor.execute_all()
    """
    
    def __init__(self, max_concurrent: int = 10):
        """
        Initialize executor.
        
        Args:
            max_concurrent: Maximum concurrent executions
        """
        self._tasks: List[ToolTask] = []
        self._max_concurrent = max_concurrent
        self._tool_registry: Dict[str, Callable] = {}
        self._semaphore: Optional[asyncio.Semaphore] = None
        logger.info(f"ParallelExecutor initialized (max_concurrent={max_concurrent})")
    
    def register_tool(self, name: str, func: Callable):
        """Register a tool function for execution."""
        self._tool_registry[name] = func
        logger.debug(f"Registered tool: {name}")
    
    def add_task(self, tool_name: str, arguments: Dict[str, Any], 
                 task_id: str = None) -> str:
        """
        Add a task to the execution queue.
        
        Args:
            tool_name: Name of tool to execute
            arguments: Tool arguments
            task_id: Optional custom task ID
            
        Returns:
            Task ID
        """
        if task_id is None:
            task_id = f"{tool_name}_{len(self._tasks)}_{datetime.now().timestamp()}"
        
        task = ToolTask(
            id=task_id,
            name=tool_name,
            arguments=arguments
        )
        self._tasks.append(task)
        return task_id
    
    def add_tasks(self, tasks: List[Dict[str, Any]]):
        """
        Add multiple tasks at once.
        
        Args:
            tasks: List of {"tool": name, "arguments": {}, "id": optional}
        """
        for t in tasks:
            self.add_task(
                tool_name=t["tool"],
                arguments=t.get("arguments", {}),
                task_id=t.get("id")
            )
    
    async def execute_all(self, timeout_per_task: int = 60) -> ParallelResult:
        """
        Execute all pending tasks in parallel.
        
        Args:
            timeout_per_task: Timeout per task in seconds
            
        Returns:
            ParallelResult with all task results
        """
        if not self._tasks:
            return ParallelResult(
                tasks=[],
                total_time_ms=0,
                success_count=0,
                failed_count=0,
                cancelled_count=0
            )
        
        start_time = datetime.now()
        
        # Create semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
        
        # Create tasks
        async def run_task(task: ToolTask):
            async with self._semaphore:
                await self._execute_single(task, timeout_per_task)
        
        # Execute all in parallel
        await asyncio.gather(*[run_task(t) for t in self._tasks], return_exceptions=True)
        
        total_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        success = sum(1 for t in self._tasks if t.status == ToolStatus.COMPLETED)
        failed = sum(1 for t in self._tasks if t.status == ToolStatus.FAILED)
        cancelled = sum(1 for t in self._tasks if t.status == ToolStatus.CANCELLED)
        
        logger.info(
            f"Parallel execution complete: {success} success, {failed} failed, "
            f"{cancelled} cancelled in {total_time}ms"
        )
        
        return ParallelResult(
            tasks=self._tasks,
            total_time_ms=total_time,
            success_count=success,
            failed_count=failed,
            cancelled_count=cancelled
        )
    
    async def _execute_single(self, task: ToolTask, timeout: int):
        """Execute a single task."""
        task.status = ToolStatus.RUNNING
        task.started_at = datetime.now()
        
        if task.name not in self._tool_registry:
            task.status = ToolStatus.FAILED
            task.error = f"Tool not registered: {task.name}"
            task.completed_at = datetime.now()
            return
        
        tool_func = self._tool_registry[task.name]
        
        try:
            # Execute with timeout
            if asyncio.iscoroutinefunction(tool_func):
                result = await asyncio.wait_for(
                    tool_func(**task.arguments),
                    timeout=timeout
                )
            else:
                # Run sync function in executor
                loop = asyncio.get_event_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: tool_func(**task.arguments)),
                    timeout=timeout
                )
            
            task.result = result
            task.status = ToolStatus.COMPLETED
            
        except asyncio.TimeoutError:
            task.status = ToolStatus.FAILED
            task.error = f"Timeout after {timeout}s"
            
        except Exception as e:
            task.status = ToolStatus.FAILED
            task.error = str(e)
        
        task.completed_at = datetime.now()
        task.execution_time_ms = int(
            (task.completed_at - task.started_at).total_seconds() * 1000
        )
    
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending task."""
        for task in self._tasks:
            if task.id == task_id and task.status == ToolStatus.PENDING:
                task.status = ToolStatus.CANCELLED
                task.completed_at = datetime.now()
                return True
        return False
    
    def cancel_all(self):
        """Cancel all pending tasks."""
        for task in self._tasks:
            if task.status == ToolStatus.PENDING:
                task.status = ToolStatus.CANCELLED
                task.completed_at = datetime.now()
    
    def get_results(self) -> List[Dict[str, Any]]:
        """Get all task results."""
        return [
            {
                "id": t.id,
                "name": t.name,
                "status": t.status.value,
                "result": t.result,
                "error": t.error,
                "execution_time_ms": t.execution_time_ms
            }
            for t in self._tasks
        ]
    
    def get_successful_results(self) -> List[Any]:
        """Get only successful results."""
        return [t.result for t in self._tasks if t.status == ToolStatus.COMPLETED]
    
    def clear(self):
        """Clear all tasks."""
        self._tasks = []


# Utility: Check if tools can be parallelized
def can_parallelize(tool_calls: List[Dict[str, Any]]) -> tuple[bool, List[List[int]]]:
    """
    Analyze tool calls for parallelization opportunities.
    
    Returns:
        (can_parallelize, groups_of_parallel_ids)
    """
    # Simple heuristic: all tool calls can be parallel unless they depend on each other
    # In real implementation, would analyze arguments for dependencies
    
    if not tool_calls:
        return False, []
    
    # All can run in parallel if no explicit dependencies
    return True, [list(range(len(tool_calls)))]


# Quick parallel helper
async def run_parallel(tools: List[Dict[str, Any]], 
                       tool_registry: Dict[str, Callable],
                       max_concurrent: int = 10) -> List[Any]:
    """
    Quick helper for running tools in parallel.
    
    Args:
        tools: List of {"tool": name, "arguments": {}}
        tool_registry: Dict of tool_name -> function
        max_concurrent: Max concurrent executions
        
    Returns:
        List of results in same order as input
    """
    executor = ParallelToolExecutor(max_concurrent=max_concurrent)
    
    for tool in tools:
        executor.register_tool(tool["tool"], tool_registry[tool["tool"]])
        executor.add_task(tool["tool"], tool.get("arguments", {}))
    
    result = await executor.execute_all()
    
    # Return results in order
    return [
        t.result if t.status == ToolStatus.COMPLETED else None
        for t in result.tasks
    ]
