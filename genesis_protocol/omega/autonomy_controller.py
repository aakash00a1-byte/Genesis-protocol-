"""Autonomy Controller - GLUTTONY OMEGA

Reduces human dependence over time through proven reliability."""

from typing import Dict, List


class AutonomyController:
    """Controls autonomy level based on trust and reliability."""
    
    # Actions by autonomy level required
    AUTONOMY_LEVELS = {
        0.0: [],  # Human only
        0.2: ["observe", "read", "search"],  # Basic reading
        0.4: ["calculate", "analyze", "recommend"],  # Analysis
        0.6: ["experiment", "propose", "plan"],  # Proposal
        0.8: ["prepare", "test", "benchmark"],  # Preparation
        1.0: ["execute_trusted"]  # Full autonomy (requires max trust)
    }
    
    # Forbidden actions (never autonomous)
    FORBIDDEN_AUTONOMOUS = [
        "spend_money",
        "purchase",
        "access_secrets",
        "auto_deploy",
        "auto_modify_code",
        "disable_safety",
        "delete_memories"
    ]
    
    def __init__(self):
        self.current_level = 0.3  # Start conservative
        self.trusted_actions = set()
    
    def can_execute(self, action: str) -> bool:
        """Check if action can be executed at current autonomy level."""
        # Forbidden actions never autonomous
        if action in self.FORBIDDEN_AUTONOMOUS:
            return False
        
        # Check if enough autonomy level
        for level in sorted(self.AUTONOMY_LEVELS.keys()):
            if self.current_level >= level:
                allowed = self.AUTONOMY_LEVELS[level]
                if action in allowed or "execute_trusted" in allowed:
                    return True
        return False
    
    def set_level(self, level: float):
        """Set autonomy level (0-1)."""
        self.current_level = max(0.0, min(1.0, level))
    
    def increase_level(self, delta: float = 0.05):
        """Increase autonomy level."""
        self.current_level = min(1.0, self.current_level + delta)
    
    def decrease_level(self, delta: float = 0.1):
        """Decrease autonomy level after failure."""
        self.current_level = max(0.0, self.current_level - delta)
    
    def trust_action(self, action: str):
        """Mark action as trusted."""
        self.trusted_actions.add(action)
    
    def get_level(self) -> float:
        """Get current autonomy level."""
        return self.current_level
    
    def get_allowed_actions(self) -> List[str]:
        """Get list of allowed actions at current level."""
        allowed = []
        for level in sorted(self.AUTONOMY_LEVELS.keys()):
            if self.current_level >= level:
                allowed.extend(self.AUTONOMY_LEVELS[level])
        return list(set(allowed))
    
    def get_status(self) -> Dict:
        """Get autonomy status."""
        return {
            "level": self.current_level,
            "allowed_actions": self.get_allowed_actions(),
            "trusted_actions": list(self.trusted_actions),
            "forbidden": self.FORBIDDEN_AUTONOMOUS
        }


_autonomy_controller: AutonomyController = None


def get_autonomy_controller() -> AutonomyController:
    global _autonomy_controller
    if _autonomy_controller is None:
        _autonomy_controller = AutonomyController()
    return _autonomy_controller
