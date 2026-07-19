"""Genesis Protocol - Critic / Self-Critique System

Evaluate responses before sending using a critic model.
Based on OpenHands critic pattern.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

logger = logging.getLogger("critic")


class CritiqueLevel(Enum):
    """Critique depth levels."""
    NONE = "none"
    QUICK = "quick"      # Basic quality check
    STANDARD = "standard" # Full critique
    THOROUGH = "thorough" # Deep analysis with refinement


@dataclass
class CritiqueResult:
    """Result of critique evaluation."""
    approved: bool
    score: float  # 0.0 - 1.0
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    improved_response: Optional[str] = None
    critique_time_ms: int = 0


@dataclass
class CritiqueCriteria:
    """Criteria for evaluation."""
    check_accuracy: bool = True
    check_relevance: bool = True
    check_tone: bool = True
    check_completeness: bool = True
    check_safety: bool = True
    min_score: float = 0.7


class ResponseCritic:
    """
    Critic system for evaluating and improving responses.
    
    Features:
    - Pre-flight quality checks
    - Safety validation
    - Tone/voice consistency
    - Auto-improvement suggestions
    - Iterative refinement
    """
    
    # Quick check patterns for fast validation
    NEGATIVE_PATTERNS = [
        "i'm sorry", "i apologize", "as an ai", "as a language model",
        "i cannot", "i'm unable", "i'm not able to"
    ]
    
    POSITIVE_PATTERNS = [
        "definitely", "absolutely", "here's", "here is",
        "you can", "i'll", "let me"
    ]
    
    def __init__(self, llm_callable: Callable = None, enable_refinement: bool = True):
        """
        Initialize response critic.
        
        Args:
            llm_callable: Optional LLM for deep critique
            enable_refinement: Enable auto-improvement suggestions
        """
        self._llm = llm_callable
        self._enable_refinement = enable_refinement
        self._critique_count = 0
        self._approval_count = 0
        logger.info("ResponseCritic initialized")
    
    async def critique(self, response: str, context: Dict[str, Any] = None,
                      level: CritiqueLevel = CritiqueLevel.STANDARD,
                      criteria: CritiqueCriteria = None) -> CritiqueResult:
        """
        Critique a response.
        
        Args:
            response: The response to critique
            context: Optional context (user message, conversation history)
            level: Critique depth level
            criteria: Evaluation criteria
            
        Returns:
            CritiqueResult with evaluation
        """
        import time
        start = time.time()
        
        criteria = criteria or CritiqueCriteria()
        issues = []
        suggestions = []
        score = 1.0
        
        # Level-specific checks
        if level == CritiqueLevel.NONE:
            return CritiqueResult(approved=True, score=1.0, critique_time_ms=0)
        
        # Quick checks (always run)
        if level in [CritiqueLevel.QUICK, CritiqueLevel.STANDARD, CritiqueLevel.THOROUGH]:
            q_issues, q_score = self._quick_checks(response)
            issues.extend(q_issues)
            score = min(score, q_score)
        
        # Standard checks
        if level in [CritiqueLevel.STANDARD, CritiqueLevel.THOROUGH]:
            if criteria.check_safety:
                safety_issues, safety_score = self._safety_check(response)
                issues.extend(safety_issues)
                score = min(score, safety_score)
            
            if criteria.check_tone:
                tone_issues, tone_score = self._tone_check(response)
                issues.extend(tone_issues)
                score = min(score, tone_score)
        
        # Thorough checks (LLM required)
        if level == CritiqueLevel.THOROUGH and self._llm:
            l_issues, l_suggestions, l_score = await self._llm_critique(
                response, context, criteria
            )
            issues.extend(l_issues)
            suggestions.extend(l_suggestions)
            score = min(score, l_score)
            
            # Auto-refine if enabled
            if self._enable_refinement and score < criteria.min_score:
                improved = await self._refine_response(response, context, issues)
                if improved:
                    suggestions.append(f"Refined response: {improved[:50]}...")
        
        critique_time = int((time.time() - start) * 1000)
        approved = score >= criteria.min_score and len(issues) == 0
        
        self._critique_count += 1
        if approved:
            self._approval_count += 1
        
        logger.debug(
            f"Critique complete: score={score:.2f}, "
            f"approved={approved}, issues={len(issues)}, time={critique_time}ms"
        )
        
        return CritiqueResult(
            approved=approved,
            score=score,
            issues=issues,
            suggestions=suggestions,
            critique_time_ms=critique_time
        )
    
    def _quick_checks(self, response: str) -> tuple:
        """Quick pattern-based checks."""
        issues = []
        score = 1.0
        
        response_lower = response.lower()
        
        # Check for negative AI patterns
        for pattern in self.NEGATIVE_PATTERNS:
            if pattern in response_lower:
                issues.append(f"Contains deflection pattern: '{pattern}'")
                score -= 0.15
        
        # Check minimum length
        if len(response) < 20:
            issues.append("Response too short")
            score -= 0.2
        
        # Check for excessive repetition
        words = response.split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.5:
                issues.append("Excessive word repetition detected")
                score -= 0.2
        
        # Check for placeholder text
        if "[TODO]" in response or "[INSERT" in response:
            issues.append("Contains placeholder text")
            score -= 0.3
        
        score = max(0.0, min(1.0, score))
        return issues, score
    
    def _safety_check(self, response: str) -> tuple:
        """Safety and policy checks."""
        issues = []
        score = 1.0
        
        response_lower = response.lower()
        
        # Dangerous content patterns
        dangerous = [
            "how to hack", "how to break", "exploit vulnerability",
            "steal from", "illegal ways to"
        ]
        
        for pattern in dangerous:
            if pattern in response_lower:
                issues.append(f"Potentially unsafe content: '{pattern}'")
                score -= 0.4
        
        # Check for harmful advice
        if "always" in response_lower and any(x in response_lower for x in ["kill", "destroy", "harm"]):
            issues.append("Contains potentially harmful absolute statements")
            score -= 0.3
        
        score = max(0.0, min(1.0, score))
        return issues, score
    
    def _tone_check(self, response: str) -> tuple:
        """Tone and voice consistency checks."""
        issues = []
        score = 1.0
        
        # Check for mixed formality
        has_very_formal = any(x in response for x in ["therefore", "consequently", "henceforth"])
        has_very_informal = any(x in response.lower() for x in ["lol", "omg", "btw"])
        
        if has_very_formal and has_very_informal:
            issues.append("Mixed formality levels")
            score -= 0.1
        
        # Check for all caps (except acronyms)
        words = response.split()
        caps_words = [w for w in words if w.isupper() and len(w) > 2]
        if len(caps_words) > 5:
            issues.append("Excessive use of capital letters")
            score -= 0.1
        
        # Check for excessive punctuation
        if "!!!" in response or "???" in response:
            issues.append("Excessive punctuation detected")
            score -= 0.05
        
        score = max(0.0, min(1.0, score))
        return issues, score
    
    async def _llm_critique(self, response: str, context: Dict[str, Any],
                           criteria: CritiqueCriteria) -> tuple:
        """Deep LLM-based critique."""
        if not self._llm:
            return [], [], 1.0
        
        try:
            prompt = f"""Critique this AI response:

RESPONSE: {response}

CONTEXT: {context or {}}

Evaluate on:
1. Accuracy - Is the information correct?
2. Relevance - Does it address the user's question?
3. Completeness - Is it thorough enough?
4. Helpfulness - Is it actually useful?

Respond with JSON:
{{
  "issues": ["list of specific issues"],
  "suggestions": ["list of improvement suggestions"],
  "score": 0.0-1.0
}}"""
            
            result = await self._llm([{"role": "user", "content": prompt}])
            
            # Parse result (simplified)
            if isinstance(result, dict):
                return (
                    result.get("issues", []),
                    result.get("suggestions", []),
                    result.get("score", 0.8)
                )
            
            return [], [], 0.8
            
        except Exception as e:
            logger.error(f"LLM critique failed: {e}")
            return [], [], 1.0
    
    async def _refine_response(self, response: str, context: Dict[str, Any],
                               issues: List[str]) -> Optional[str]:
        """Refine response based on issues."""
        if not self._llm:
            return None
        
        try:
            prompt = f"""Improve this response to fix these issues:
{chr(10).join(f"- {i}" for i in issues)}

ORIGINAL: {response}

CONTEXT: {context or {}}

Provide an improved version that addresses these issues while maintaining the helpful tone."""
            
            improved = await self._llm([{"role": "user", "content": prompt}])
            
            if isinstance(improved, str):
                return improved
            elif isinstance(improved, dict):
                return improved.get("content")
            
            return None
            
        except Exception as e:
            logger.error(f"Response refinement failed: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get critic statistics."""
        approval_rate = (
            self._approval_count / self._critique_count 
            if self._critique_count > 0 else 0
        )
        
        return {
            "total_critiques": self._critique_count,
            "approved": self._approval_count,
            "rejected": self._critique_count - self._approval_count,
            "approval_rate": approval_rate,
            "refinement_enabled": self._enable_refinement
        }


# Singleton
_critic: Optional[ResponseCritic] = None


def get_critic(llm_callable: Callable = None) -> ResponseCritic:
    """Get global response critic."""
    global _critic
    if _critic is None:
        _critic = ResponseCritic(llm_callable)
    return _critic


# Decorator for automatic critique
def critiqued(critic: ResponseCritic = None, level: CritiqueLevel = CritiqueLevel.STANDARD):
    """Decorator for automatic response critique."""
    if critic is None:
        critic = get_critic()
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Assume response is last arg or result
            response = result if isinstance(result, str) else kwargs.get("response", "")
            
            if response and isinstance(response, str):
                critique_result = await critic.critique(response, level=level)
                if not critique_result.approved:
                    logger.warning(
                        f"Response not approved: {critique_result.issues}"
                    )
            
            return result
        return wrapper
    return decorator
