"""Survival Manager - GLUTTONY v3.0 Survival Layer"""
from .resource_monitor import get_resource_monitor
from .cost_tracker import get_cost_tracker
from .quota_tracker import get_quota_tracker
from .expiration_detector import get_expiration_detector
from .risk_score import get_risk_score


class SurvivalManager:
    def __init__(self):
        self.resources = get_resource_monitor()
        self.costs = get_cost_tracker()
        self.quotas = get_quota_tracker()
        self.expiration = get_expiration_detector()
        self.risk = get_risk_score()
    
    def get_full_status(self) -> dict:
        return {
            "resources": self.resources.get_all_stats(),
            "costs": {"total": self.costs.get_total(), "today": self.costs.get_today()},
            "quotas": self.quotas.get_all_status(),
            "expiring": len(self.expiration.check_expiring()),
            "expired": len(self.expiration.check_expired())
        }


_survival_manager = None
def get_survival_manager() -> SurvivalManager:
    global _survival_manager
    if _survival_manager is None:
        _survival_manager = SurvivalManager()
    return _survival_manager
