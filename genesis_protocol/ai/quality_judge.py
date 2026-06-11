"""Genesis Protocol - Quality Judge System

Response evaluation layer that scores outputs based on:
- correctness
- completeness
- clarity
- intent match

Low scores trigger regeneration with next best model.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum

from genesis_protocol.utils.logger import get_logger

logger = get_logger("ai.quality_judge")


class QualityLevel(Enum):
    """Quality classification levels."""
    EXCELLENT = 0.9
    GOOD = 0.75
    ACCEPTABLE = 0.6
    POOR = 0.4
    FAILED = 0.2


@dataclass
class QualityReport:
    """Detailed quality assessment."""
    overall_score: float
    correctness: float
    completeness: float
    clarity: float
    intent_match: float
    issues: List[str]
    suggestions: List[str]
    level: QualityLevel


class QualityJudge:
    """
    Quality Judge System for response evaluation.
    
    Evaluates responses against criteria and provides
    detailed feedback. Low scores trigger regeneration.
    """
    
    # Minimum acceptable quality threshold
    MIN_THRESHOLD = 0.6
    
    # Issue patterns
    INCOMPLETE_PATTERNS = [
        r'\.\.\.$',  # Ends with ellipsis
        r'(TODO|FIXME|placeholder)',  # Placeholder text
        r'(incomplete|not\s+finished|to\s+be\s+continued)',  # Explicit incomplete
    ]
    
    UNCLEAR_PATTERNS = [
        r'\b(maybe|perhaps|possibly|not\s+sure)\b',  # Uncertainty
        r'(I\s+don\'t\s+know|I\'m\s+not\s+sure)',  # Unknown
        r'(vague|unclear|confusing)',  # Explicit unclear
    ]
    
    INCORRECT_PATTERNS = [
        r'(wrong|incorrect|error|mistake)',  # Self-admitted errors
        r'(should\s+verify|check\s+this)',  # Unverified claims
    ]
    
    # Generic response patterns (low quality indicator)
    GENERIC_PATTERNS = [
        r'^yes,?\s*i\s+can\s+help',
        r'^of\s+course',
        r'^sure,?\s*(I|here)',
        r'^absolutely',
        r'^hello!?\s*(I\s+am|how\s+can)',
        r'^as\s+an\s+AI',
        r'^I\'m\s+(an\s+)?AI',
    ]
    
    def __init__(self):
        """Initialize quality judge."""
        self.logger = logging.getLogger("ai.quality_judge")
        self._evaluation_history: List[QualityReport] = []
    
    async def judge(self, response: str, criteria: List[str], 
                    intent: str = "", context: str = "") -> float:
        """
        Judge response quality.
        
        Args:
            response: The response to evaluate
            criteria: Success criteria to check against
            intent: Original user intent
            context: Additional context
            
        Returns:
            Overall quality score (0.0 to 1.0)
        """
        if not response:
            return 0.0
        
        # Calculate individual scores
        correctness = self._evaluate_correctness(response)
        completeness = self._evaluate_completeness(response, criteria)
        clarity = self._evaluate_clarity(response)
        intent_match = self._evaluate_intent_match(response, intent)
        
        # Calculate overall score (weighted average)
        overall = (
            correctness * 0.25 +
            completeness * 0.30 +
            clarity * 0.20 +
            intent_match * 0.25
        )
        
        # Detect issues
        issues = self._detect_issues(response)
        
        # Generate suggestions
        suggestions = self._generate_suggestions(issues, overall)
        
        # Determine level
        level = QualityLevel.EXCELLENT
        if overall >= 0.9:
            level = QualityLevel.EXCELLENT
        elif overall >= 0.75:
            level = QualityLevel.GOOD
        elif overall >= 0.6:
            level = QualityLevel.ACCEPTABLE
        elif overall >= 0.4:
            level = QualityLevel.POOR
        else:
            level = QualityLevel.FAILED
        
        # Create report
        report = QualityReport(
            overall_score=overall,
            correctness=correctness,
            completeness=completeness,
            clarity=clarity,
            intent_match=intent_match,
            issues=issues,
            suggestions=suggestions,
            level=level
        )
        
        self._evaluation_history.append(report)
        
        self.logger.info(f"Quality judged: {overall:.2f} ({level.name})")
        
        return overall
    
    def _evaluate_correctness(self, response: str) -> float:
        """Evaluate correctness of response."""
        score = 1.0
        
        # Check for self-admitted errors
        if re.search(r'(wrong|incorrect|error|mistake)', response.lower()):
            score -= 0.3
        
        # Check for unverified claims
        if re.search(r'(should\s+verify|check\s+this)', response.lower()):
            score -= 0.2
        
        # Check for placeholder text
        if re.search(r'(TODO|FIXME|placeholder|TBD)', response):
            score -= 0.4
        
        return max(0.0, score)
    
    def _evaluate_completeness(self, response: str, criteria: List[str]) -> float:
        """Evaluate completeness of response."""
        score = 1.0
        
        # Check for incomplete indicators
        for pattern in self.INCOMPLETE_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                score -= 0.3
                break
        
        # Check response length (too short = incomplete)
        if len(response) < 50:
            score -= 0.2
        elif len(response) < 100:
            score -= 0.1
        
        # Check for question marks in intent but no answers
        # (Assuming if user asked "how", there should be explanation)
        # This is heuristic-based
        
        return max(0.0, score)
    
    def _evaluate_clarity(self, response: str) -> float:
        """Evaluate clarity of response."""
        score = 1.0
        
        # Check for unclear language
        for pattern in self.UNCLEAR_PATTERNS:
            if re.search(pattern, response.lower()):
                score -= 0.2
                break
        
        # Check for generic/boilerplate responses
        for pattern in self.GENERIC_PATTERNS:
            if re.match(pattern, response.lower()):
                score -= 0.3
                break
        
        # Check for excessive length without structure
        if len(response) > 1000:
            # Look for structure (bullets, numbered lists)
            if not re.search(r'[\n•\d]+\s', response):
                score -= 0.1
        
        return max(0.0, score)
    
    def _evaluate_intent_match(self, response: str, intent: str) -> float:
        """Evaluate how well response matches user intent."""
        if not intent:
            return 0.8  # No intent to match against
        
        intent_lower = intent.lower()
        response_lower = response.lower()
        
        score = 0.7  # Base score
        
        # Check key intent words in response
        intent_keywords = [
            'code' if 'code' in intent_lower else None,
            'explain' if 'explain' in intent_lower else None,
            'create' if 'create' in intent_lower else None,
            'help' if 'help' in intent_lower else None,
            'build' if 'build' in intent_lower else None,
        ]
        intent_keywords = [k for k in intent_keywords if k]
        
        if intent_keywords:
            keywords_found = sum(1 for kw in intent_keywords if kw in response_lower)
            keyword_score = keywords_found / len(intent_keywords)
            score = 0.5 + (keyword_score * 0.4)  # Range: 0.5 to 0.9
        
        return max(0.0, min(1.0, score))
    
    def _detect_issues(self, response: str) -> List[str]:
        """Detect specific issues in response."""
        issues = []
        
        # Check each issue pattern
        if re.search(r'\.\.\.$', response):
            issues.append("response_ends_incomplete")
        
        if re.search(r'(TODO|FIXME|placeholder|TBD)', response):
            issues.append("contains_placeholder_text")
        
        if re.search(r'(I\s+don\'t\s+know|I\'m\s+not\s+sure)', response.lower()):
            issues.append("expresses_uncertainty")
        
        if re.match(r'^(yes,?\s*i\s+can|of\s+course|sure)', response.lower()):
            issues.append("generic_opening")
        
        if len(response) < 50:
            issues.append("response_too_short")
        
        if len(response) > 2000 and not re.search(r'[\n•\d]+', response):
            issues.append("lacks_structured_format")
        
        return issues
    
    def _generate_suggestions(self, issues: List[str], overall: float) -> List[str]:
        """Generate improvement suggestions based on issues."""
        suggestions = []
        
        if overall < 0.6:
            suggestions.append("Consider regenerating with alternative model")
        
        if "response_ends_incomplete" in issues:
            suggestions.append("Complete the response fully")
        
        if "contains_placeholder_text" in issues:
            suggestions.append("Replace placeholder text with actual content")
        
        if "expresses_uncertainty" in issues:
            suggestions.append("Provide confident, factual answers")
        
        if "generic_opening" in issues:
            suggestions.append("Start with direct content, skip introductions")
        
        if "response_too_short" in issues:
            suggestions.append("Expand response with more detail")
        
        if "lacks_structured_format" in issues:
            suggestions.append("Use bullet points or numbered lists for clarity")
        
        return suggestions
    
    def should_regenerate(self, quality_score: float) -> bool:
        """Determine if response should be regenerated."""
        return quality_score < self.MIN_THRESHOLD
    
    def get_best_alternative(self, current_model: str, 
                            available_models: List[str]) -> Optional[str]:
        """
        Get best alternative model for regeneration.
        
        Args:
            current_model: Currently used model
            available_models: List of available model names
            
        Returns:
            Best alternative model name or None
        """
        # Simple ranking - in production, use scoring engine
        ranking = ["gpt-4o", "gemini-1.5-pro", "claude-3-5-sonnet-20241022", 
                   "gemini-2.0-flash", "llama-3.3-70b-versatile"]
        
        alternatives = [m for m in ranking if m in available_models and m != current_model]
        
        return alternatives[0] if alternatives else None
    
    def get_history(self) -> List[QualityReport]:
        """Get evaluation history for analysis."""
        return self._evaluation_history
    
    def get_average_quality(self, last_n: int = 100) -> float:
        """Get average quality score over last N evaluations."""
        history = self._evaluation_history[-last_n:]
        if not history:
            return 0.0
        
        return sum(r.overall_score for r in history) / len(history)


# Singleton
_quality_judge: Optional[QualityJudge] = None


def get_quality_judge() -> QualityJudge:
    """Get or create quality judge singleton."""
    global _quality_judge
    if _quality_judge is None:
        _quality_judge = QualityJudge()
    return _quality_judge