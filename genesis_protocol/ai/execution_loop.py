"""Genesis Protocol - Execution Loop

Implements the Plan → Execute → Verify → Improve loop
for autonomous agent behavior.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from genesis_protocol.ai.task_planner import (
    TaskPlanner, TaskPlan, TaskStep, TaskStatus, get_task_planner
)
from genesis_protocol.ai.quality_judge import QualityJudge, get_quality_judge
from genesis_protocol.ai.tool_system import ToolSystem, get_tool_system
from genesis_protocol.ai.scoring_engine import get_scoring_engine
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.execution_loop")


@dataclass
class LoopState:
    """Current state of execution loop."""
    plan_id: str
    current_step: int
    iterations: int
    max_iterations: int
    quality_scores: List[float]
    improving: bool = False


class ExecutionLoop:
    """
    Autonomous execution loop implementing Plan → Execute → Verify → Improve.
    
    Runs iteratively until task is complete or success criteria met.
    """
    
    MAX_ITERATIONS = 5
    MIN_QUALITY_THRESHOLD = 0.6
    IMPROVEMENT_ATTEMPTS = 2
    
    def __init__(self):
        """Initialize execution loop."""
        self.task_planner = get_task_planner()
        self.quality_judge = get_quality_judge()
        self.tool_system = get_tool_system()
        self.scoring = get_scoring_engine()
        self.logger = logging.getLogger("ai.execution_loop")
        self._active_loops: Dict[str, LoopState] = {}
    
    async def execute_plan(self, query: str, mode: str = "auto",
                          context: str = "") -> Dict[str, Any]:
        """
        Execute a task plan through the execution loop.
        
        Args:
            query: User request
            mode: Execution mode (auto or manual)
            context: Additional context
            
        Returns:
            Dict with results and metadata
        """
        # Check if already have a plan for this user
        plan_id = f"{hash(query) % 1000000}"
        
        # Create or get plan
        if plan_id in self._active_loops:
            plan = self.task_planner.get_plan(plan_id)
            if not plan:
                plan = self.task_planner.create_plan(query, mode)
        else:
            plan = self.task_planner.create_plan(query, mode)
        
        # Initialize loop state
        loop_state = LoopState(
            plan_id=plan_id,
            current_step=0,
            iterations=0,
            max_iterations=self.MAX_ITERATIONS,
            quality_scores=[]
        )
        self._active_loops[plan_id] = loop_state
        
        results = []
        final_output = ""
        
        self.logger.info(f"Starting execution loop for plan: {plan.task_type.value}")
        
        # Execute each step
        while loop_state.current_step < len(plan.steps):
            if loop_state.iterations >= loop_state.max_iterations:
                self.logger.warning("Max iterations reached")
                break
            
            step = plan.steps[loop_state.current_step]
            self.logger.info(f"Executing step {step.id}: {step.description}")
            
            # Execute step
            step_result = await self._execute_step(step, context, results)
            
            if step_result.success:
                # Verify step quality
                quality_score = await self._verify_step(step, step_result.output, plan)
                loop_state.quality_scores.append(quality_score)
                
                # If quality is low, try to improve
                if quality_score < self.MIN_QUALITY_THRESHOLD and not loop_state.improving:
                    self.logger.info(f"Low quality ({quality_score:.2f}), attempting improvement")
                    improved = await self._improve_step(step, step_result.output, context, results)
                    if improved:
                        step_result.output = improved
                        loop_state.quality_scores[-1] = await self._verify_step(step, improved, plan)
                
                # Record success
                self.task_planner.update_plan_status(
                    plan_id, step.id, TaskStatus.COMPLETED, 
                    str(step_result.output)
                )
                results.append({
                    "step": step.id,
                    "description": step.description,
                    "output": step_result.output,
                    "quality": loop_state.quality_scores[-1],
                    "model": step_result.model_used,
                    "tool": step_result.tool_used
                })
                
                final_output = step_result.output
            else:
                self.logger.error(f"Step {step.id} failed: {step_result.error}")
                self.task_planner.update_plan_status(
                    plan_id, step.id, TaskStatus.FAILED, 
                    error=str(step_result.error)
                )
                results.append({
                    "step": step.id,
                    "description": step.description,
                    "error": step_result.error
                })
            
            loop_state.current_step += 1
            loop_state.iterations += 1
        
        # Generate final response
        return await self._generate_final_response(plan, results, final_output)
    
    async def _execute_step(self, step: TaskStep, context: str,
                           previous_results: List[Dict]) -> Any:
        """Execute a single step."""
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        try:
            # Determine if tool should be used
            if step.action in ["web_search", "code_execution", "memory_store", 
                              "memory_recall", "file_reader"]:
                tool_result = await self.tool_system.execute_tool(
                    step.tool_name or step.action,
                    self._extract_tool_params(step.description, context)
                )
                return tool_result
            
            # Use LLM for analysis, generation, response
            provider_chain = get_provider_chain()
            
            # Build context from previous results
            history_context = self._build_history_context(previous_results)
            
            # Build prompt
            prompt = self._build_step_prompt(step, context, history_context)
            
            # Execute with LLM
            result = await provider_chain.call(
                messages=[
                    {"role": "system", "content": self._get_system_prompt_for_action(step.action)},
                    {"role": "user", "content": prompt}
                ],
                user_input=step.description,
                model=step.model_preference
            )
            
            if result.success:
                return result
            else:
                return type('obj', (object,), {
                    'success': False,
                    'error': result.error
                })()
        
        except Exception as e:
            self.logger.error(f"Step execution error: {e}")
            return type('obj', (object,), {'success': False, 'error': str(e)})()
    
    async def _verify_step(self, step: TaskStep, output: Any, 
                          plan: TaskPlan) -> float:
        """Verify step output quality."""
        if isinstance(output, str):
            # Judge string output
            quality = await self.quality_judge.judge(
                response=output,
                criteria=plan.success_criteria,
                intent=step.description
            )
        elif hasattr(output, 'data'):
            # Tool result
            quality = 0.8 if output.success else 0.3
        else:
            quality = 0.5
        
        return quality
    
    async def _improve_step(self, step: TaskStep, current_output: str,
                           context: str, previous_results: List[Dict]) -> Optional[str]:
        """Attempt to improve step output."""
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        for attempt in range(self.IMPROVEMENT_ATTEMPTS):
            self.logger.info(f"Improvement attempt {attempt + 1}")
            
            provider_chain = get_provider_chain()
            
            # Get next best model
            scored = self.scoring.score_models(
                step.description,
                type('obj', (object,), {'primary_intent': 'reasoning', 'sub_intents': [], 
                                      'complexity': 0.7})(),
                provider_chain.get_available_providers()
            )
            
            # Skip current model
            alternatives = [s for s in scored if s.model_name != step.model_preference]
            
            if not alternatives:
                break
            
            alt_model = alternatives[0]
            
            # Try with alternative model
            result = await provider_chain.call(
                messages=[
                    {"role": "system", "content": f"Previous response was inadequate. Improve it.\n\nOriginal: {current_output}"},
                    {"role": "user", "content": f"Improve this response: {step.description}"}
                ],
                preferred_provider=alt_model.provider,
                model=alt_model.model_name,
                user_input=step.description
            )
            
            if result.success:
                quality = await self.quality_judge.judge(
                    result.response.content,
                    ["is improved", "addresses request"],
                    step.description
                )
                
                if quality >= self.MIN_QUALITY_THRESHOLD:
                    return result.response.content
        
        return None
    
    def _build_history_context(self, results: List[Dict]) -> str:
        """Build context from previous step results."""
        if not results:
            return ""
        
        context = "Previous steps completed:\n"
        for r in results:
            context += f"- {r.get('description', 'Step')}: {r.get('output', r.get('error', ''))[:200]}\n"
        
        return context
    
    def _build_step_prompt(self, step: TaskStep, context: str, 
                          history: str) -> str:
        """Build prompt for step execution."""
        prompt = f"Task: {step.description}\n"
        
        if context:
            prompt += f"\nContext: {context}\n"
        
        if history:
            prompt += f"\n{history}\n"
        
        prompt += "\nProvide a clear, direct response."
        
        return prompt
    
    def _get_system_prompt_for_action(self, action: str) -> str:
        """Get system prompt for action type."""
        prompts = {
            "llm_analysis": "You are an analysis module. Analyze the request and provide insights. Be concise and direct. Hinglish responses preferred.",
            "llm_generation": "You are a generation module. Create high-quality output based on the task. No self-introduction. Direct answers only.",
            "llm_verification": "You are a verification module. Check the output for correctness and completeness. Provide feedback.",
            "llm_response": "You are Genesis. Give direct, concise responses in Hinglish. No AI explanations.",
            "llm_synthesis": "You are a synthesis module. Combine information and present it clearly."
        }
        return prompts.get(action, "You are Genesis. Direct, concise responses in Hinglish.")
    
    def _extract_tool_params(self, description: str, context: str) -> Dict:
        """Extract parameters for tool execution."""
        params = {}
        
        # Simple extraction for web search
        if "search" in description.lower() or "research" in description.lower():
            params["query"] = context or description
        
        return params
    
    async def _generate_final_response(self, plan: TaskPlan, 
                                       results: List[Dict],
                                       final_output: str) -> Dict[str, Any]:
        """Generate final response from execution results."""
        # Calculate overall quality
        quality_scores = [r.get("quality", 0) for r in results if "quality" in r]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        return {
            "success": plan.completed,
            "response": final_output,
            "task_type": plan.task_type.value,
            "steps_completed": len([r for r in results if "error" not in r]),
            "total_steps": len(plan.steps),
            "quality_score": avg_quality,
            "iterations": results[-1].get("step", 0) + 1 if results else 0,
            "mode": plan.mode,
            "step_results": results
        }


# Singleton
_execution_loop: Optional[ExecutionLoop] = None


def get_execution_loop() -> ExecutionLoop:
    """Get or create execution loop singleton."""
    global _execution_loop
    if _execution_loop is None:
        _execution_loop = ExecutionLoop()
    return _execution_loop