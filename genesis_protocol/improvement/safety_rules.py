"""Safety Rules - Genesis Protocol v1.7"""

from typing import List


class SafetyRules:
    FORBIDDEN_ACTIONS = [
        "auto_deploy",
        "auto_modify_code", 
        "delete_memory",
        "disable_safety",
        "modify_auth",
        "access_credentials",
        "execute_arbitrary_code",
    ]
    
    REQUIRES_APPROVAL = [
        "modify_core",
        "add_dependency",
        "change_api",
        "modify_database",
    ]
    
    def __init__(self):
        self.enabled = True
    
    def is_allowed(self, action: str) -> bool:
        if not self.enabled:
            return False
        return action not in self.FORBIDDEN_ACTIONS
    
    def requires_approval(self, action: str) -> bool:
        return action in self.REQUIRES_APPROVAL
    
    def get_status(self) -> dict:
        return {
            "enabled": self.enabled,
            "forbidden_count": len(self.FORBIDDEN_ACTIONS),
            "approval_required_count": len(self.REQUIRES_APPROVAL)
        }


_safety_rules = None


def get_safety_rules() -> SafetyRules:
    global _safety_rules
    if _safety_rules is None:
        _safety_rules = SafetyRules()
    return _safety_rules
