"""Genesis Protocol - 2-Stage Reasoning Pipeline

Stage 1: Planning - Generate solution plan
Stage 2: Execution - Generate final response
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from genesis_protocol.ai.scoring_engine import get_scoring_engine, IntentAnalysis
from genesis_protocol.ai.provider_chain import get_provider_chain, AICallResult
from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.reasoning")


class ResponseQuality(Enum):
    """Response quality assessment."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    FAILED = "failed"


@dataclass
class Plan:
    """Solution plan from Stage 1."""
    approach: str
    steps: List[str]
    tools_to_use: List[str]
    estimated_complexity: float
    preferred_model: str


@dataclass
class ExecutionResult:
    """Result from Stage 2 execution."""
    response: str
    quality: ResponseQuality
    model_used: str
    provider_used: str
    latency_ms: int
    retry_count: int = 0
    quality_issues: List[str] = None
    
    def __post_init__(self):
        if self.quality_issues is None:
            self.quality_issues = []


@dataclass
class ReasoningResult:
    """Complete result from 2-stage reasoning."""
    success: bool
    response: str
    quality: ResponseQuality
    plan: Optional[Plan] = None
    execution: Optional[ExecutionResult] = None
    error: Optional[str] = None
    stages_completed: int = 0


class TwoStageReasoning:
    """
    2-Stage Reasoning Pipeline.
    
    Stage 1 (Planning): Analyze query, create solution plan
    Stage 2 (Execution): Generate response based on plan
    """
    
    PLANNING_PROMPT = """You are Genesis planning module. Analyze the user's request and create a brief solution plan.

User Query: {query}

Recent Context: {context}

Respond ONLY with a JSON plan in this format (no other text):
{{"approach": "brief description", "steps": ["step1", "step2"], "tools": ["tool1"], "complexity": 0.5}}

Keep plan concise. If query is simple, set complexity to 0.1."""


class ReasoningPipeline:
    """
    Complete reasoning pipeline with 2-stage processing.
    
    - Analyzes intent using scoring engine
    - Optionally bypasses planning for simple queries
    - Executes with reflection and retry
    """
    
    def __init__(self):
        """Initialize reasoning pipeline."""
        self.scoring = get_scoring_engine()
        self.provider_chain = get_provider_chain()
        self.logger = logging.getLogger("ai.reasoning")
        self._reflection_threshold = 0.4  # Min acceptable quality
    
    async def process(self, query: str, context: str = "", 
                      bypass_planning: bool = False) -> ReasoningResult:
        """
        Process query through 2-stage reasoning.
        
        Args:
            query: User query
            context: Conversation context
            bypass_planning: Skip Stage 1 for simple queries
            
        Returns:
            ReasoningResult with final response
        """
        # Analyze intent
        intent = self.scoring.analyze_intent(query)
        
        # Check for simple query bypass
        if self.scoring.is_simple_query(query):
            bypass_planning = True
        
        plan = None
        stages_completed = 0
        
        # Stage 1: Planning (if not bypassed)
        if not bypass_planning and intent.complexity > 0.3:
            plan = await self._stage1_planning(query, context, intent)
            stages_completed = 1
        
        # Stage 2: Execution
        execution = await self._stage2_execution(query, context, intent, plan)
        stages_completed += 1
        
        # Reflection check - retry if poor quality
        if execution.quality in [ResponseQuality.POOR, ResponseQuality.FAILED]:
            self.logger.info(f"Poor quality response, attempting retry...")
            execution = await self._retry_with_alternative(
                query, context, intent, execution
            )
        
        return ReasoningResult(
            success=execution.quality not in [ResponseQuality.POOR, ResponseQuality.FAILED],
            response=execution.response,
            quality=execution.quality,
            plan=plan,
            execution=execution,
            stages_completed=stages_completed
        )
    
    async def _stage1_planning(self, query: str, context: str, 
                              intent: IntentAnalysis) -> Optional[Plan]:
        """Stage 1: Generate solution plan."""
        try:
            # Use Gemini for fast planning
            messages = [
                {"role": "system", "content": self.PLANNING_PROMPT.format(
                    query=query,
                    context=context[:500] if context else "No prior context"
                )}
            ]
            
            result = await self.provider_chain.call(
                messages=messages,
                preferred_provider="gemini",
                user_input=query
            )
            
            if result.success:
                # Parse plan from response
                import json
                try:
                    plan_data = json.loads(result.response.content)
                    return Plan(
                        approach=plan_data.get("approach", "general"),
                        steps=plan_data.get("steps", []),
                        tools_to_use=plan_data.get("tools", []),
                        estimated_complexity=plan_data.get("complexity", 0.5),
                        preferred_model=plan_data.get("model", "gemini-2.0-flash")
                    )
                except json.JSONDecodeError:
                    self.logger.warning("Could not parse plan JSON")
                    return None
            else:
                self.logger.warning(f"Planning failed: {result.error}")
                return None
                
        except Exception as e:
            self.logger.error(f"Planning stage error: {e}")
            return None
    
    async def _stage2_execution(self, query: str, context: str,
                               intent: IntentAnalysis,
                               plan: Optional[Plan] = None) -> ExecutionResult:
        """Stage 2: Generate final response."""
        # Get model selection from scoring engine
        provider, model, score, _ = self.scoring.select_model(
            query, 
            self.provider_chain.get_available_providers()
        )
        
        # Build system prompt
        system_prompt = self._build_system_prompt(plan)
        
        # Build messages
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        if context:
            messages.append({"role": "system", "content": f"Context: {context}"})
        
        messages.append({"role": "user", "content": query})
        
        # Execute
        result = await self.provider_chain.call(
            messages=messages,
            preferred_provider=provider,
            model=model,
            user_input=query
        )
        
        if not result.success:
            return ExecutionResult(
                response="",
                quality=ResponseQuality.FAILED,
                model_used=model,
                provider_used=provider,
                latency_ms=result.total_latency_ms,
                quality_issues=["All providers failed"]
            )
        
        # Evaluate quality
        quality, issues = self._evaluate_response(result.response.content, intent)
        
        return ExecutionResult(
            response=result.response.content,
            quality=quality,
            model_used=result.model_used or model,
            provider_used=result.provider_used or provider,
            latency_ms=result.total_latency_ms,
            quality_issues=issues
        )
    
    async def _retry_with_alternative(self, query: str, context: str,
                                       intent: IntentAnalysis,
                                       failed_execution: ExecutionResult) -> ExecutionResult:
        """Retry execution with alternative model."""
        # Get fallback chain
        scored = self.scoring.score_models(
            query, intent, 
            self.provider_chain.get_available_providers()
        )
        
        # Skip already tried model
        alternatives = [s for s in scored if s.model_name != failed_execution.model_used]
        
        for alt in alternatives[:3]:  # Try top 3 alternatives
            self.logger.info(f"Retrying with {alt.model_name}...")
            
            system_prompt = self._build_system_prompt(None)
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            if context:
                messages.append({"role": "system", "content": f"Context: {context}"})
            messages.append({"role": "user", "content": query})
            
            result = await self.provider_chain.call(
                messages=messages,
                preferred_provider=alt.provider,
                model=alt.model_name,
                user_input=query
            )
            
            if result.success:
                quality, issues = self._evaluate_response(result.response.content, intent)
                
                if quality not in [ResponseQuality.POOR, ResponseQuality.FAILED]:
                    return ExecutionResult(
                        response=result.response.content,
                        quality=quality,
                        model_used=result.model_used or alt.model_name,
                        provider_used=result.provider_used or alt.provider,
                        latency_ms=result.total_latency_ms,
                        retry_count=failed_execution.retry_count + 1,
                        quality_issues=issues
                    )
        
        # All retries failed, return best attempt
        return ExecutionResult(
            response=failed_execution.response or "Service temporarily unavailable. Please try again.",
            quality=ResponseQuality.ACCEPTABLE,
            model_used=failed_execution.model_used,
            provider_used=failed_execution.provider_used,
            latency_ms=failed_execution.latency_ms,
            retry_count=failed_execution.retry_count + 1,
            quality_issues=["Max retries exceeded"]
        )
    
    def _build_system_prompt(self, plan: Optional[Plan] = None) -> str:
        """Build system prompt for execution."""
        base_prompt = """You are Genesis. 

**RESPONSE STYLE - CRITICAL:**
- NEVER say "I am an AI" or "As an AI assistant"
- NEVER introduce yourself
- Give DIRECT, CONCISE answers only
- No generic disclaimers
- Hinglish (Hindi+English mix) by default

"""
        
        if plan and plan.approach:
            base_prompt += f"\n**Plan:** {plan.approach}\n"
            if plan.steps:
                base_prompt += f"**Approach:** {' -> '.join(plan.steps)}\n"
        
        return base_prompt
    
    def _evaluate_response(self, response: str, intent: IntentAnalysis) -> Tuple[ResponseQuality, List[str]]:
        """Evaluate response quality."""
        issues = []
        quality_scores = []
        
        # Length check
        if len(response) < 20:
            issues.append("response_too_short")
            quality_scores.append(0.2)
        elif len(response) < 50:
            quality_scores.append(0.5)
        else:
            quality_scores.append(0.8)
        
        # Completeness check
        question_words = ["what", "why", "how", "when", "where", "who", "which"]
        has_question = any(w in intent.primary_intent or w in str(intent.sub_intents) 
                         for w in question_words)
        
        if has_question and len(response) < 100:
            issues.append("incomplete_answer")
            quality_scores.append(0.3)
        
        # Confidence indicators
        low_confidence_phrases = ["i'm not sure", "i don't know", "perhaps", "maybe", "possibly"]
        if any(phrase in response.lower() for phrase in low_confidence_phrases):
            quality_scores.append(0.5)
            issues.append("low_confidence")
        
        # Generic response check
        generic_patterns = [
            r"^yes,?\s+i\s+can\s+help",
            r"^sure,?\s+i'?ll",
            r"^of\s+course",
            r"^absolutely",
        ]
        if any(re.match(p, response.lower()) for p in generic_patterns):
            issues.append("generic_response")
            quality_scores.append(0.4)
        
        # Calculate overall quality
        if not quality_scores:
            avg_score = 0.7
        else:
            avg_score = sum(quality_scores) / len(quality_scores)
        
        if avg_score >= 0.8:
            quality = ResponseQuality.EXCELLENT
        elif avg_score >= 0.6:
            quality = ResponseQuality.GOOD
        elif avg_score >= 0.4:
            quality = ResponseQuality.ACCEPTABLE
        else:
            quality = ResponseQuality.POOR
        
        return quality, issues


# Singleton
_reasoning_pipeline: Optional[ReasoningPipeline] = None


def get_reasoning_pipeline() -> ReasoningPipeline:
    """Get or create reasoning pipeline singleton."""
    global _reasoning_pipeline
    if _reasoning_pipeline is None:
        _reasoning_pipeline = ReasoningPipeline()
    return _reasoning_pipeline