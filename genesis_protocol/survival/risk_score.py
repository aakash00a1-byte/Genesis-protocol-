"""Risk Score - GLUTTONY v3.0 Survival Layer"""
from typing import Dict, List


class RiskScore:
    def __init__(self):
        self._scores = []
    
    def calculate(self, action: str, context: Dict) -> Dict:
        risk_factors = {"high": 0.3, "medium": 0.2, "low": 0.1}
        base_risk = risk_factors.get(context.get("risk_level", "low"), 0.1)
        has_rollback = 1 if context.get("rollback_possible") else 0
        has_approval = 1 if context.get("has_approval") else 0
        final_score = base_risk * (1 - has_rollback * 0.3) * (1 - has_approval * 0.5)
        return {
            "action": action,
            "score": min(final_score, 1.0),
            "level": "high" if final_score > 0.2 else "medium" if final_score > 0.1 else "low",
            "factors": context
        }
    
    def get_history(self) -> List[Dict]:
        return self._scores


_risk_score = None
def get_risk_score() -> RiskScore:
    global _risk_score
    if _risk_score is None:
        _risk_score = RiskScore()
    return _risk_score
