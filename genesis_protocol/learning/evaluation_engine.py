"""Conversation Evaluation Engine - Genesis Protocol v1.5
Records and evaluates every response for quality metrics."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class ResponseQuality(Enum):
    """Quality rating for responses."""
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    POOR = "poor"
    FAILED = "failed"


class FeedbackType(Enum):
    """Types of user feedback."""
    EXPLICIT_POSITIVE = "explicit_positive"
    EXPLICIT_NEGATIVE = "explicit_negative"
    IMPLICIT_POSITIVE = "implicit_positive"
    IMPLICIT_NEGATIVE = "implicit_negative"
    NEUTRAL = "neutral"


@dataclass
class EvaluationResult:
    """Result of a conversation evaluation."""
    conversation_id: str
    timestamp: datetime
    response_quality: ResponseQuality
    quality_score: float  # 0.0 - 1.0
    
    # Metrics
    latency_ms: float
    provider_used: str
    success: bool
    error_message: Optional[str] = None
    
    # Content analysis
    response_length: int = 0
    contains_code: bool = False
    contains_emoji: bool = False
    used_humor: bool = False
    
    # Feedback
    feedback_type: FeedbackType = FeedbackType.NEUTRAL
    user_feedback_text: Optional[str] = None
    
    # Context
    persona: str = "unknown"
    mood: str = "unknown"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'conversation_id': self.conversation_id,
            'timestamp': self.timestamp.isoformat(),
            'quality': self.response_quality.value,
            'quality_score': self.quality_score,
            'latency_ms': self.latency_ms,
            'provider': self.provider_used,
            'success': self.success,
            'error': self.error_message,
            'response_length': self.response_length,
            'contains_code': self.contains_code,
            'contains_emoji': self.contains_emoji,
            'used_humor': self.used_humor,
            'feedback': self.feedback_type.value,
            'persona': self.persona,
            'mood': self.mood
        }


class ConversationEvaluation:
    """Evaluates conversation responses and tracks quality metrics."""
    
    def __init__(self, storage_path: str = "./data/evaluations"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._evaluations: List[EvaluationResult] = []
        self._conversation_counter = 0
        self._load_evaluations()
    
    def _load_evaluations(self):
        """Load recent evaluations from disk."""
        eval_file = self.storage_path / "evaluations.json"
        if eval_file.exists():
            try:
                with open(eval_file, 'r') as f:
                    data = json.load(f)
                # Convert to EvaluationResult objects
                for item in data[-100:]:
                    item['timestamp'] = datetime.fromisoformat(item['timestamp'])
                    item['response_quality'] = ResponseQuality(item['quality'])
                    item['feedback_type'] = FeedbackType(item['feedback'])
                    self._evaluations.append(EvaluationResult(**item))
            except Exception:
                pass
    
    def _save_evaluations(self):
        """Save evaluations to disk."""
        eval_file = self.storage_path / "evaluations.json"
        data = [e.to_dict() for e in self._evaluations[-500:]]  # Keep last 500
        try:
            with open(eval_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def evaluate(
        self,
        message: str,
        response: str,
        latency_ms: float,
        provider: str,
        success: bool,
        error: Optional[str] = None,
        persona: str = "unknown",
        mood: str = "unknown",
        user_feedback: Optional[str] = None
    ) -> EvaluationResult:
        """Evaluate a conversation response."""
        self._conversation_counter += 1
        conversation_id = f"conv_{self._conversation_counter}_{datetime.now().strftime('%Y%m%d')}"
        
        # Analyze response
        response_length = len(response)
        contains_code = '```' in response or 'def ' in response or 'class ' in response
        contains_emoji = any(c in response for c in '😀😄🎉😎🔥✨💻')
        used_humor = any(word in response.lower() for word in ['haha', 'lol', '😄', 'fun'])
        
        # Calculate quality score
        quality_score = self._calculate_quality_score(
            success=success,
            latency_ms=latency_ms,
            response_length=response_length,
            contains_code=contains_code
        )
        
        # Determine quality level
        if not success:
            quality = ResponseQuality.FAILED
        elif quality_score >= 0.8:
            quality = ResponseQuality.EXCELLENT
        elif quality_score >= 0.6:
            quality = ResponseQuality.GOOD
        elif quality_score >= 0.4:
            quality = ResponseQuality.AVERAGE
        else:
            quality = ResponseQuality.POOR
        
        # Detect feedback type
        feedback_type = self._detect_feedback(user_feedback, message)
        
        result = EvaluationResult(
            conversation_id=conversation_id,
            timestamp=datetime.now(),
            response_quality=quality,
            quality_score=quality_score,
            latency_ms=latency_ms,
            provider_used=provider,
            success=success,
            error_message=error,
            response_length=response_length,
            contains_code=contains_code,
            contains_emoji=contains_emoji,
            used_humor=used_humor,
            feedback_type=feedback_type,
            user_feedback_text=user_feedback,
            persona=persona,
            mood=mood
        )
        
        self._evaluations.append(result)
        if len(self._evaluations) > 500:
            self._evaluations = self._evaluations[-500:]
        self._save_evaluations()
        
        return result
    
    def _calculate_quality_score(
        self,
        success: bool,
        latency_ms: float,
        response_length: int,
        contains_code: bool
    ) -> float:
        """Calculate quality score 0.0 - 1.0"""
        if not success:
            return 0.0
        
        score = 0.0
        
        # Success contributes 40%
        score += 0.4
        
        # Latency contributes 20% (faster = better)
        if latency_ms < 1000:
            score += 0.2
        elif latency_ms < 3000:
            score += 0.15
        elif latency_ms < 5000:
            score += 0.1
        else:
            score += 0.05
        
        # Response length contributes 20% (not too short, not too long)
        if 50 <= response_length <= 500:
            score += 0.2
        elif 20 <= response_length <= 1000:
            score += 0.15
        elif response_length > 0:
            score += 0.1
        
        # Code presence contributes 20%
        if contains_code:
            score += 0.2
        
        return min(1.0, score)
    
    def _detect_feedback(self, feedback: Optional[str], message: str) -> FeedbackType:
        """Detect feedback type from feedback or message."""
        if feedback:
            feedback_lower = feedback.lower()
            if any(word in feedback_lower for word in ['great', 'thanks', 'perfect', 'awesome', 'good']):
                return FeedbackType.EXPLICIT_POSITIVE
            if any(word in feedback_lower for word in ['bad', 'wrong', 'terrible', 'disappointed']):
                return FeedbackType.EXPLICIT_NEGATIVE
        
        # Implicit feedback from message
        message_lower = message.lower()
        if any(word in message_lower for word in ['thanks', 'great', 'perfect']):
            return FeedbackType.IMPLICIT_POSITIVE
        if any(word in message_lower for word in ['wrong', 'fix', 'again', 'not what']):
            return FeedbackType.IMPLICIT_NEGATIVE
        
        return FeedbackType.NEUTRAL
    
    def get_recent_evaluations(self, limit: int = 20) -> List[EvaluationResult]:
        """Get recent evaluations."""
        return self._evaluations[-limit:]
    
    def get_average_quality(self, limit: int = 100) -> float:
        """Get average quality score."""
        recent = self._evaluations[-limit:]
        if not recent:
            return 0.0
        return sum(e.quality_score for e in recent) / len(recent)
    
    def get_success_rate(self, limit: int = 100) -> float:
        """Get success rate."""
        recent = self._evaluations[-limit:]
        if not recent:
            return 0.0
        successful = sum(1 for e in recent if e.success)
        return successful / len(recent)
    
    def get_average_latency(self, limit: int = 100) -> float:
        """Get average latency."""
        recent = [e for e in self._evaluations[-limit:] if e.success]
        if not recent:
            return 0.0
        return sum(e.latency_ms for e in recent) / len(recent)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get evaluation statistics."""
        if not self._evaluations:
            return {'total_conversations': 0}
        
        recent_100 = self._evaluations[-100:]
        
        return {
            'total_conversations': len(self._evaluations),
            'average_quality': self.get_average_quality(),
            'success_rate': self.get_success_rate(),
            'average_latency_ms': self.get_average_latency(),
            'quality_distribution': {
                'excellent': sum(1 for e in recent_100 if e.response_quality == ResponseQuality.EXCELLENT),
                'good': sum(1 for e in recent_100 if e.response_quality == ResponseQuality.GOOD),
                'average': sum(1 for e in recent_100 if e.response_quality == ResponseQuality.AVERAGE),
                'poor': sum(1 for e in recent_100 if e.response_quality == ResponseQuality.POOR),
                'failed': sum(1 for e in recent_100 if e.response_quality == ResponseQuality.FAILED),
            },
            'provider_usage': self._get_provider_stats(),
            'feedback_distribution': self._get_feedback_stats()
        }
    
    def _get_provider_stats(self) -> Dict[str, int]:
        """Get provider usage statistics."""
        recent = self._evaluations[-100:]
        stats = {}
        for e in recent:
            stats[e.provider_used] = stats.get(e.provider_used, 0) + 1
        return stats
    
    def _get_feedback_stats(self) -> Dict[str, int]:
        """Get feedback distribution."""
        recent = self._evaluations[-100:]
        stats = {}
        for e in recent:
            fb = e.feedback_type.value
            stats[fb] = stats.get(fb, 0) + 1
        return stats


# Global singleton
_evaluation_engine: Optional[ConversationEvaluation] = None


def get_evaluation_engine() -> ConversationEvaluation:
    """Get global evaluation engine."""
    global _evaluation_engine
    if _evaluation_engine is None:
        _evaluation_engine = ConversationEvaluation()
    return _evaluation_engine
