"""Genesis Protocol - Goal Completion Loop

Self-continuing execution until goal is verified complete.
Based on OpenHands goal completion pattern.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum

logger = logging.getLogger("goal_completion")


class GoalStatus(Enum):
    """Goal execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_ITERATIONS = "max_iterations"


@dataclass
class Goal:
    """A goal to achieve."""
    goal_id: str
    description: str
    success_criteria: str  # Description of what "done" looks like
    created_at: datetime = field(default_factory=datetime.utcnow)
    iterations: int = 0
    max_iterations: int = 10
    status: GoalStatus = GoalStatus.PENDING
    history: List[Dict] = field(default_factory=list)
    final_result: Any = None


@dataclass
class GoalResult:
    """Result of goal execution."""
    success: bool
    goal: Goal
    iterations_used: int
    final_result: Any
    verification_output: Optional[str] = None
    execution_time_seconds: float = 0


class GoalCompletionLoop:
    """
    Goal-driven execution with automatic verification.
    
    Features:
    - Define goals with success criteria
    - Self-iterating execution
    - Automatic verification
    - Max iteration limits
    - History tracking
    """
    
    def __init__(self, executor: Callable = None, verifier: Callable = None):
        """
        Initialize goal completion loop.
        
        Args:
            executor: Function to execute one iteration
                     signature: (goal, context) -> result
            verifier: Function to verify goal completion
                     signature: (goal, result) -> (success, output)
        """
        self._executor = executor
        self._verifier = verifier
        self._active_goals: Dict[str, Goal] = {}
        self._completed_goals: List[Goal] = []
        logger.info("GoalCompletionLoop initialized")
    
    def set_executor(self, executor: Callable):
        """Set the executor function."""
        self._executor = executor
    
    def set_verifier(self, verifier: Callable):
        """Set the verifier function."""
        self._verifier = verifier
    
    async def execute_goal(
        self,
        description: str,
        success_criteria: str,
        context: Dict[str, Any] = None,
        max_iterations: int = 10,
        verify_interval: int = 1
    ) -> GoalResult:
        """
        Execute a goal until completion.
        
        Args:
            description: What to achieve
            success_criteria: How to know it's done
            context: Additional context for execution
            max_iterations: Maximum iterations before giving up
            verify_interval: Verify every N iterations
            
        Returns:
            GoalResult with outcome
        """
        import time
        start = time.time()
        
        goal = Goal(
            goal_id=f"goal_{len(self._completed_goals) + 1}",
            description=description,
            success_criteria=success_criteria,
            max_iterations=max_iterations,
            status=GoalStatus.IN_PROGRESS
        )
        
        self._active_goals[goal.goal_id] = goal
        context = context or {}
        
        logger.info(f"Starting goal: {goal.goal_id} - {description}")
        
        last_result = None
        
        while goal.iterations < max_iterations:
            goal.iterations += 1
            
            logger.debug(f"Goal {goal.goal_id} iteration {goal.iterations}/{max_iterations}")
            
            # Execute iteration
            try:
                if self._executor:
                    iteration_result = await self._executor(goal, context, last_result)
                    last_result = iteration_result
                else:
                    iteration_result = {"status": "no_executor", "iteration": goal.iterations}
                    last_result = iteration_result
                
                # Record history
                goal.history.append({
                    "iteration": goal.iterations,
                    "timestamp": datetime.utcnow().isoformat(),
                    "result": str(iteration_result)[:200]  # Truncate for storage
                })
                
                # Verify at interval
                if goal.iterations % verify_interval == 0 or goal.iterations == max_iterations:
                    goal.status = GoalStatus.VERIFYING
                    success, verification_output = await self._verify(goal, last_result)
                    
                    if success:
                        goal.status = GoalStatus.COMPLETED
                        goal.final_result = last_result
                        
                        execution_time = time.time() - start
                        
                        logger.info(
                            f"Goal {goal.goal_id} COMPLETED in {goal.iterations} iterations "
                            f"({execution_time:.2f}s)"
                        )
                        
                        self._active_goals.pop(goal.goal_id, None)
                        self._completed_goals.append(goal)
                        
                        return GoalResult(
                            success=True,
                            goal=goal,
                            iterations_used=goal.iterations,
                            final_result=last_result,
                            verification_output=verification_output,
                            execution_time_seconds=execution_time
                        )
                
                # Small delay between iterations
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Goal {goal.goal_id} iteration error: {e}")
                goal.history.append({
                    "iteration": goal.iterations,
                    "timestamp": datetime.utcnow().isoformat(),
                    "error": str(e)
                })
        
        # Max iterations reached
        goal.status = GoalStatus.MAX_ITERATIONS
        
        execution_time = time.time() - start
        
        logger.warning(
            f"Goal {goal.goal_id} MAX ITERATIONS reached ({max_iterations})"
        )
        
        self._active_goals.pop(goal.goal_id, None)
        self._completed_goals.append(goal)
        
        return GoalResult(
            success=False,
            goal=goal,
            iterations_used=goal.iterations,
            final_result=last_result,
            execution_time_seconds=execution_time
        )
    
    async def _verify(self, goal: Goal, result: Any) -> tuple:
        """
        Verify if goal is complete.
        
        Args:
            goal: The goal
            result: Current result
            
        Returns:
            (success, verification_output)
        """
        if self._verifier:
            try:
                return await self._verifier(goal, result)
            except Exception as e:
                logger.error(f"Verifier error: {e}")
        
        # Default verification (always returns False to continue)
        return False, "No verifier configured"
    
    def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Get goal by ID."""
        return self._active_goals.get(goal_id)
    
    def list_active_goals(self) -> List[Goal]:
        """List all active goals."""
        return list(self._active_goals.values())
    
    def list_completed_goals(self, limit: int = 50) -> List[Goal]:
        """List completed goals."""
        return self._completed_goals[-limit:]
    
    def cancel_goal(self, goal_id: str) -> bool:
        """Cancel an active goal."""
        if goal_id in self._active_goals:
            goal = self._active_goals[goal_id]
            goal.status = GoalStatus.FAILED
            self._active_goals.pop(goal_id, None)
            self._completed_goals.append(goal)
            logger.info(f"Cancelled goal: {goal_id}")
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get goal completion statistics."""
        total = len(self._completed_goals)
        completed = sum(1 for g in self._completed_goals if g.status == GoalStatus.COMPLETED)
        failed = sum(1 for g in self._completed_goals if g.status in [
            GoalStatus.FAILED, GoalStatus.MAX_ITERATIONS
        ])
        
        avg_iterations = (
            sum(g.iterations for g in self._completed_goals) / total 
            if total > 0 else 0
        )
        
        return {
            "total_goals": total,
            "completed": completed,
            "failed": failed,
            "active": len(self._active_goals),
            "success_rate": completed / total if total > 0 else 0,
            "average_iterations": avg_iterations
        }


# Singleton
_goal_loop: Optional[GoalCompletionLoop] = None


def get_goal_loop() -> GoalCompletionLoop:
    """Get global goal completion loop."""
    global _goal_loop
    if _goal_loop is None:
        _goal_loop = GoalCompletionLoop()
    return _goal_loop


# Example: Simple code fix goal executor
async def code_fix_executor(goal: Goal, context: Dict, last_result: Any) -> Dict:
    """
    Example executor for fixing code issues.
    
    Returns dict with:
    - fixed: Whether code was fixed
    - attempts: Number of fix attempts made
    - status: Current status
    """
    attempts = goal.iterations
    
    # Simulate fixing code
    if attempts >= 3:
        return {"fixed": True, "attempts": attempts, "status": "success"}
    else:
        return {"fixed": False, "attempts": attempts, "status": "in_progress"}


async def code_fix_verifier(goal: Goal, result: Any) -> tuple:
    """Verify code fix is complete."""
    if isinstance(result, dict) and result.get("fixed"):
        return True, "Code successfully fixed!"
    return False, "Code still needs fixes"
