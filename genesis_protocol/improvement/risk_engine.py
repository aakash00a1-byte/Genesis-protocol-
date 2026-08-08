"""Risk Engine - Genesis Protocol v1.7"""

from typing import Dict, List, Any
from enum import Enum


class RiskLevel(Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    DANGEROUS = "dangerous"


class RiskEngine:
    def __init__(self):
        self.safe_files = ["tests/", "docs/", "data/", "config/"]
        self.dangerous_files = ["auth", "security", "password", "key", "secret"]
    
    def assess_risk(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        solution = proposal.get("proposed_solution", "")
        files = proposal.get("files_affected", [])
        risk_score = 0.0
        factors = []
        
        for f in files:
            if any(s in f for s in self.safe_files):
                risk_score += 0.1
                factors.append(f"Safe: {f}")
            elif any(d in f.lower() for d in self.dangerous_files):
                risk_score += 0.8
                factors.append(f"Dangerous: {f}")
        
        if any(p in solution.lower() for p in ["eval(", "exec(", "rm -rf"]):
            risk_score += 0.7
            factors.append("Dangerous pattern")
        
        level = RiskLevel.SAFE if risk_score < 0.3 else RiskLevel.MODERATE if risk_score < 0.6 else RiskLevel.DANGEROUS
        
        return {
            "risk_level": level.value,
            "risk_score": min(1.0, risk_score),
            "factors": factors
        }
    
    def can_auto_approve(self, proposal: Dict[str, Any]) -> bool:
        return self.assess_risk(proposal)["risk_level"] == "safe"


_risk_engine = None


def get_risk_engine() -> RiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
