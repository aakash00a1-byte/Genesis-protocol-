"""Confidence Engine - Genesis Protocol v1.8"""

from typing import Dict, List, Any


class ConfidenceEngine:
    """Computes confidence scores for proposals."""
    
    def __init__(self):
        self.base_confidence = 0.5
    
    def compute_confidence(
        self,
        evidence: List[Dict],
        risk_level: str,
        historical_success: float = 0.0
    ) -> Dict[str, Any]:
        """Compute confidence score from various factors."""
        
        # Evidence weight
        evidence_score = min(1.0, len(evidence) * 0.15)
        
        # Risk adjustment
        risk_adjustment = {
            "safe": 0.2,
            "moderate": 0.0,
            "dangerous": -0.3
        }.get(risk_level, 0.0)
        
        # Historical adjustment
        historical_score = historical_success * 0.2
        
        # Calculate final confidence
        confidence = (
            self.base_confidence +
            evidence_score +
            risk_adjustment +
            historical_score
        )
        confidence = max(0.0, min(1.0, confidence))
        
        # Estimate impact
        impact = self._estimate_impact(evidence, risk_level)
        
        # Probability of success
        success_prob = self._estimate_success_probability(
            confidence, risk_level, len(evidence)
        )
        
        return {
            "confidence": round(confidence, 2),
            "evidence_strength": round(evidence_score, 2),
            "estimated_impact": impact,
            "success_probability": round(success_prob, 2),
            "factors": {
                "evidence_count": len(evidence),
                "risk_level": risk_level,
                "historical_success": historical_success
            }
        }
    
    def _estimate_impact(self, evidence: List[Dict], risk_level: str) -> str:
        """Estimate the impact of the proposal."""
        if not evidence:
            return "low"
        
        if risk_level == "dangerous":
            return "uncertain"
        
        if len(evidence) >= 5:
            return "high"
        elif len(evidence) >= 3:
            return "medium"
        return "low"
    
    def _estimate_success_probability(
        self,
        confidence: float,
        risk_level: str,
        evidence_count: int
    ) -> float:
        """Estimate probability of successful implementation."""
        base = confidence
        
        if risk_level == "safe":
            base += 0.15
        elif risk_level == "dangerous":
            base -= 0.2
        
        if evidence_count >= 3:
            base += 0.1
        
        return max(0.0, min(1.0, base))


_engine = None


def get_confidence_engine() -> ConfidenceEngine:
    global _engine
    if _engine is None:
        _engine = ConfidenceEngine()
    return _engine
