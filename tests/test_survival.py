"""Tests for GLUTTONY v3.0 Survival Layer"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta


class TestResourceMonitor:
    def test_cpu_usage(self):
        from genesis_protocol.survival import get_resource_monitor
        r = get_resource_monitor()
        cpu = r.get_cpu_usage()
        assert isinstance(cpu, float)
        assert 0 <= cpu <= 100
    
    def test_memory_usage(self):
        from genesis_protocol.survival import get_resource_monitor
        r = get_resource_monitor()
        mem = r.get_memory_usage()
        assert "percent" in mem
        assert "used_mb" in mem
    
    def test_disk_usage(self):
        from genesis_protocol.survival import get_resource_monitor
        r = get_resource_monitor()
        disk = r.get_disk_usage()
        assert "percent" in disk
        assert disk["percent"] <= 100


class TestCostTracker:
    def test_track(self):
        from genesis_protocol.survival import get_cost_tracker
        c = get_cost_tracker()
        initial = c.get_total()
        c.track("groq", 100, 0.01)
        assert c.get_total() > initial
    
    def test_by_provider(self):
        from genesis_protocol.survival import get_cost_tracker
        c = get_cost_tracker()
        c.track("groq", 100, 0.05)
        cost = c.get_by_provider("groq")
        assert cost > 0


class TestQuotaTracker:
    def test_check_quota(self):
        from genesis_protocol.survival import get_quota_tracker
        q = get_quota_tracker()
        status = q.check_quota("groq")
        assert "can_proceed" in status
        assert status["can_proceed"] is True
    
    def test_record_usage(self):
        from genesis_protocol.survival import get_quota_tracker
        q = get_quota_tracker()
        q.record_usage("groq", 100)
        status = q.check_quota("groq")
        assert status["requests_remaining_min"] < 30


class TestExpirationDetector:
    def test_track(self):
        from genesis_protocol.survival import get_expiration_detector
        e = get_expiration_detector()
        e.track("test-id", "token", datetime.now() + timedelta(hours=24))
        assert len(e.get_all()) > 0
    
    def test_check_expiring(self):
        from genesis_protocol.survival import get_expiration_detector
        e = get_expiration_detector()
        e.track("expiring", "token", datetime.now() + timedelta(hours=12))
        expiring = e.check_expiring(24)
        assert len(expiring) > 0
    
    def test_check_expired(self):
        from genesis_protocol.survival import get_expiration_detector
        e = get_expiration_detector()
        e.track("expired", "token", datetime.now() - timedelta(hours=1))
        expired = e.check_expired()
        assert len(expired) > 0


class TestRiskScore:
    def test_calculate(self):
        from genesis_protocol.survival import get_risk_score
        s = get_risk_score()
        risk = s.calculate("test", {"risk_level": "low"})
        assert "score" in risk
        assert "level" in risk
    
    def test_risk_levels(self):
        from genesis_protocol.survival import get_risk_score
        s = get_risk_score()
        low = s.calculate("t", {"risk_level": "low"})
        high = s.calculate("t", {"risk_level": "high"})
        assert low["score"] < high["score"]


class TestSurvivalManager:
    def test_full_status(self):
        from genesis_protocol.survival import get_survival_manager
        m = get_survival_manager()
        status = m.get_full_status()
        assert "resources" in status
        assert "costs" in status
        assert "quotas" in status
