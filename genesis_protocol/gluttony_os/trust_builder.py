"""Trust Builder - GLUTTONY OS

Builds trust through reliability and consistency."""

from typing import Dict, List


class TrustBuilder:
    """Tracks trust-building actions and reliability."""
    
    def __init__(self):
        self.actions = []
        self.successes = 0
        self.failures = 0
        self.approvals_given = 0
        self.approvals_denied = 0
    
    def record_action(self, action: str, success: bool, context: Dict = None):
        """Record an action and its outcome."""
        self.actions.append({
            "action": action,
            "success": success,
            "context": context or {}
        })
        if success:
            self.successes += 1
        else:
            self.failures += 1
    
    def record_approval_given(self):
        self.approvals_given += 1
    
    def record_approval_denied(self):
        self.approvals_denied += 1
    
    def get_reliability_score(self) -> float:
        """Calculate reliability score (0-1)."""
        total = self.successes + self.failures
        if total == 0:
            return 0.8  # Default
        return self.successes / total
    
    def get_trust_level(self) -> float:
        """Calculate trust level based on approvals and reliability."""
        reliability = self.get_reliability_score()
        approval_ratio = 0
        total = self.approvals_given + self.approvals_denied
        if total > 0:
            approval_ratio = self.approvals_given / total
        return (reliability * 0.6) + (approval_ratio * 0.4)
    
    def get_autonomy_level(self) -> float:
        """Calculate autonomy level based on reliability."""
        reliability = self.get_reliability_score()
        # Higher reliability = more autonomy allowed
        return min(reliability * 1.2, 1.0)
    
    def get_summary(self) -> Dict:
        """Get trust summary."""
        return {
            "total_actions": len(self.actions),
            "successes": self.successes,
            "failures": self.failures,
            "reliability_score": self.get_reliability_score(),
            "trust_level": self.get_trust_level(),
            "autonomy_level": self.get_autonomy_level(),
            "approvals_given": self.approvals_given,
            "approvals_denied": self.approvals_denied
        }


_trust_builder: TrustBuilder = None


def get_trust_builder() -> TrustBuilder:
    global _trust_builder
    if _trust_builder is None:
        _trust_builder = TrustBuilder()
    return _trust_builder
