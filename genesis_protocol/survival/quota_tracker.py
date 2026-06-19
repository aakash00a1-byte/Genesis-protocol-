"""Quota Tracker - GLUTTONY v3.0 Survival Layer"""
from datetime import datetime, timedelta
from typing import Dict


class QuotaTracker:
    DEFAULT_QUOTAS = {
        "groq": {"requests_per_min": 30, "tokens_per_day": 100000},
        "openrouter": {"requests_per_min": 60, "tokens_per_day": 500000},
        "ollama": {"requests_per_min": 100, "tokens_per_day": 1000000},
        "lm_studio": {"requests_per_min": 100, "tokens_per_day": 1000000},
        "huggingface": {"requests_per_min": 30, "tokens_per_day": 100000},
    }
    
    def __init__(self):
        self._quotas = dict(self.DEFAULT_QUOTAS)
        self._usage = {p: {"requests": [], "tokens": []} for p in self._quotas}
    
    def check_quota(self, provider: str) -> Dict:
        now = datetime.now()
        minute_ago = now - timedelta(minutes=1)
        reqs = self._usage.get(provider, {}).get("requests", [])
        reqs_last_min = [r for r in reqs if r > minute_ago]
        limit = self._quotas.get(provider, {})
        return {
            "provider": provider,
            "requests_remaining_min": limit.get("requests_per_min", 0) - len(reqs_last_min),
            "can_proceed": len(reqs_last_min) < limit.get("requests_per_min", 999)
        }
    
    def record_usage(self, provider: str, tokens: int = 0):
        now = datetime.now()
        if provider not in self._usage:
            self._usage[provider] = {"requests": [], "tokens": []}
        self._usage[provider]["requests"].append(now)
        self._usage[provider]["tokens"].append(tokens)
    
    def get_all_status(self) -> Dict:
        return {p: self.check_quota(p) for p in self._quotas}


_quota_tracker = None
def get_quota_tracker() -> QuotaTracker:
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = QuotaTracker()
    return _quota_tracker
