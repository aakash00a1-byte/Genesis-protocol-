"""Genesis Protocol - Task Planner Layer

Autonomous task decomposition and planning system.
Detects multi-step requests and creates structured task plans.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from genesis_protocol.ai.scoring_engine import get_scoring_engine
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.task_planner")


class TaskType(Enum):
    """Types of tasks."""
    SIMPLE = "simple"  # Single response
    SEQUENTIAL = "sequential"  # Multi-step sequential
    PARALLEL = "parallel"  # Can be done in parallel
    RESEARCH = "research"  # Needs web search
    BUILD = "build"  # Code/project building
    LEARN = "learn"  # Learning/explanation
    CREATE = "create"  # Creative work


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskStep:
    """Individual task step."""
    id: int
    description: str
    action: str  # LLM, tool, or external
    tool_name: Optional[str] = None
    model_preference: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[str] = None
    error: Optional[str] = None
    dependencies: List[int] = field(default_factory=list)


@dataclass
class TaskPlan:
    """Complete task plan."""
    original_request: str
    task_type: TaskType
    steps: List[TaskStep]
    estimated_complexity: float
    estimated_time: str
    success_criteria: List[str]
    mode: str = "auto"  # auto or manual
    current_step: int = 0
    completed: bool = False
    iterations: int = 0


@dataclass
class ExecutionResult:
    """Result of executing a step."""
    success: bool
    output: Any
    step_id: int
    model_used: Optional[str] = None
    tool_used: Optional[str] = None
    quality_score: float = 0.0
    error: Optional[str] = None


class TaskPlanner:
    """
    Task Planner Layer for autonomous agent behavior.
    
    Detects complex requests and decomposes them into
    structured task plans with sequential execution.
    """
    
    # Complex request patterns
    COMPLEX_PATTERNS = [
        r'\b(build|create|make|develop|design)\b.*\b(app|bot|website|api|system|service)\b',
        r'\b(create|make|build)\b.*\b(python|javascript|code|program|script)\b',
        r'\b(start|setup|launch|deploy)\b.*\b(project|server|app|service)\b',
        r'\b(fix|debug|implement|add)\b.*\b(feature|function|module|component)\b',
        r'\b(learn|understand|explain|teach)\b.*\b(concept|topic|subject|area)\b',
        r'\b(research|find|search|lookup)\b.*\b(information|data|details|answers)\b',
        r'\b(write|generate|produce)\b.*\b(document|report|article|content)\b',
        r'\b(automate|schedule|set\s+up)\b.*\b(task|workflow|process|system)\b',
    ]
    
    SEQUENTIAL_MARKERS = [
        r'\b(first|then|next|after|before|finally|last)\b',
        r'\b(step\s+\d+|step\s*\d+:)\b',
        r'\b(steps?)\b.*\b(1|2|3|one|two|three)\b',
        r'\b(and\s+then|also|plus|additionally)\b',
    ]
    
    def __init__(self):
        """Initialize task planner."""
        self.scoring = get_scoring_engine()
        self.logger = logging.getLogger("ai.task_planner")
        self._active_plans: Dict[str, TaskPlan] = {}
    
    def detect_complexity(self, query: str) -> Tuple[bool, TaskType, float]:
        """
        Detect if query requires complex planning.
        
        Args:
            query: User query
            
        Returns:
            Tuple of (is_complex, task_type, complexity_score)
        """
        query_lower = query.lower()
        
        # Check for complex patterns
        is_complex = False
        complexity_score = 0.3  # Base complexity
        
        for pattern in self.COMPLEX_PATTERNS:
            if re.search(pattern, query_lower):
                is_complex = True
                complexity_score += 0.3
                break
        
        # Check for sequential markers
        for pattern in self.SEQUENTIAL_MARKERS:
            if re.search(pattern, query_lower):
                complexity_score += 0.2
        
        # Check length (longer = more complex)
        if len(query) > 200:
            complexity_score += 0.2
        
        # Multiple questions/tasks
        question_count = query.count('?') + query.count(' and ')
        if question_count > 1:
            complexity_score += 0.2
        
        complexity_score = min(1.0, complexity_score)
        
        # Determine task type
        task_type = TaskType.SIMPLE
        if is_complex or complexity_score > 0.5:
            if any(kw in query_lower for kw in ["build", "create", "make", "develop"]):
                task_type = TaskType.BUILD
            elif any(kw in query_lower for kw in ["research", "find", "search", "lookup"]):
                task_type = TaskType.RESEARCH
            elif any(kw in query_lower for kw in ["learn", "explain", "understand"]):
                task_type = TaskType.LEARN
            elif any(kw in query_lower for kw in ["write", "create", "generate"]):
                task_type = TaskType.CREATE
            elif complexity_score > 0.6:
                task_type = TaskType.SEQUENTIAL
        
        return is_complex or complexity_score > 0.5, task_type, complexity_score
    
    def create_plan(self, query: str, mode: str = "auto") -> TaskPlan:
        """
        Create a structured task plan from query.
        
        Args:
            query: User request
            mode: Planning mode (auto or manual)
            
        Returns:
            TaskPlan with steps
        """
        is_complex, task_type, complexity = self.detect_complexity(query)
        
        # For simple queries, return minimal plan
        if task_type == TaskType.SIMPLE:
            return TaskPlan(
                original_request=query,
                task_type=TaskType.SIMPLE,
                steps=[TaskStep(
                    id=0,
                    description=query,
                    action="llm_response",
                    model_preference=None
                )],
                estimated_complexity=0.2,
                estimated_time="seconds",
                success_criteria=["Response is helpful and relevant"]
            )
        
        # Generate plan based on task type
        steps = self._generate_steps(query, task_type)
        
        plan = TaskPlan(
            original_request=query,
            task_type=task_type,
            steps=steps,
            estimated_complexity=complexity,
            estimated_time=self._estimate_time(steps),
            success_criteria=self._generate_success_criteria(task_type),
            mode=mode
        )
        
        # Store plan
        plan_id = f"{datetime.utcnow().timestamp()}"
        self._active_plans[plan_id] = plan
        
        self.logger.info(f"Created plan: {task_type.value}, {len(steps)} steps")
        return plan
    
    def _generate_steps(self, query: str, task_type: TaskType) -> List[TaskStep]:
        """Generate task steps based on type."""
        steps = []
        step_id = 0
        
        if task_type == TaskType.BUILD:
            # Code/project building steps
            steps.append(TaskStep(
                id=step_id,
                description="Understand requirements and structure",
                action="llm_analysis",
                model_preference="gemini-1.5-pro"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Research best practices and patterns",
                action="web_search",
                tool_name="web_search"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Create project structure or code skeleton",
                action="llm_generation",
                model_preference="gpt-4o"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Implement core functionality",
                action="code_execution",
                tool_name="code_execution"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Test and verify implementation",
                action="llm_verification",
                model_preference="claude-3-5-sonnet-20241022"
            ))
        
        elif task_type == TaskType.RESEARCH:
            # Research steps
            steps.append(TaskStep(
                id=step_id,
                description="Identify key search terms",
                action="llm_analysis",
                model_preference="gemini-2.0-flash"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Perform web search",
                action="web_search",
                tool_name="web_search"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Analyze and synthesize results",
                action="llm_synthesis",
                model_preference="gemini-1.5-pro"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Present findings clearly",
                action="llm_response",
                model_preference=None
            ))
        
        elif task_type == TaskType.SEQUENTIAL:
            # Generic sequential steps
            steps.append(TaskStep(
                id=step_id,
                description="Analyze and break down request",
                action="llm_analysis",
                model_preference=None
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Execute primary task",
                action="llm_generation",
                model_preference=None
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Verify completeness",
                action="llm_verification",
                model_preference=None
            ))
        
        elif task_type == TaskType.LEARN:
            steps.append(TaskStep(
                id=step_id,
                description="Identify learning objectives",
                action="llm_analysis",
                model_preference="gemini-1.5-pro"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Gather relevant information",
                action="web_search",
                tool_name="web_search"
            ))
            step_id += 1
            
            steps.append(TaskStep(
                id=step_id,
                description="Explain concept clearly",
                action="llm_response",
                model_preference=None
            ))
        
        else:
            # Default single step
            steps.append(TaskStep(
                id=0,
                description=query,
                action="llm_response",
                model_preference=None
            ))
        
        return steps
    
    def _estimate_time(self, steps: List[TaskStep]) -> str:
        """Estimate completion time."""
        count = len(steps)
        if count <= 1:
            return "seconds"
        elif count == 2:
            return "1-2 minutes"
        elif count <= 4:
            return "2-5 minutes"
        else:
            return "5+ minutes"
    
    def _generate_success_criteria(self, task_type: TaskType) -> List[str]:
        """Generate success criteria for task type."""
        base_criteria = {
            TaskType.BUILD: [
                "Code is syntactically correct",
                "Implements requested functionality",
                "Follows best practices",
                "Is executable/runable"
            ],
            TaskType.RESEARCH: [
                "Information is accurate and current",
                "Sources are credible",
                "Answer is comprehensive",
                "Covers all aspects of query"
            ],
            TaskType.SEQUENTIAL: [
                "All steps completed",
                "Output is coherent",
                "Goal is achieved"
            ],
            TaskType.LEARN: [
                "Concept is clearly explained",
                "Examples provided",
                "Beginner-friendly"
            ],
            TaskType.CREATE: [
                "Content is creative",
                "Follows requested format",
                "Is high quality"
            ],
            TaskType.SIMPLE: [
                "Response is helpful",
                "Addresses user query"
            ]
        }
        return base_criteria.get(task_type, base_criteria[TaskType.SIMPLE])
    
    def get_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Get existing plan by ID."""
        return self._active_plans.get(plan_id)
    
    def update_plan_status(self, plan_id: str, step_id: int, 
                          status: TaskStatus, result: str = None, error: str = None):
        """Update plan step status."""
        plan = self._active_plans.get(plan_id)
        if plan and step_id < len(plan.steps):
            plan.steps[step_id].status = status
            plan.steps[step_id].result = result
            plan.steps[step_id].error = error
            
            if status == TaskStatus.COMPLETED:
                plan.current_step = step_id + 1
            
            # Check if all steps completed
            all_done = all(s.status == TaskStatus.COMPLETED for s in plan.steps)
            plan.completed = all_done


# Singleton
_task_planner: Optional[TaskPlanner] = None


def get_task_planner() -> TaskPlanner:
    """Get or create task planner singleton."""
    global _task_planner
    if _task_planner is None:
        _task_planner = TaskPlanner()
    return _task_planner