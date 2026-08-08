"""Tests for GLUTTONY OS"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSelfKnowledge:
    def test_identity(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        identity = sk.get_identity()
        assert identity["name"] == "GLUTTONY"
        assert "purpose" in identity
    
    def test_add_lesson(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        sk.add_lesson("Test lesson")
        assert len(sk.get_lessons()) > 0
    
    def test_record_failure(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        sk.record_failure({"type": "test", "description": "Test failure"})
        assert len(sk.get_failures()) > 0
    
    def test_record_success(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        sk.record_success({"type": "test", "description": "Test success"})
        assert len(sk.get_successes()) > 0
    
    def test_metrics(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        metrics = sk.get_metrics()
        assert "trust_level" in metrics
        assert "autonomy_level" in metrics
    
    def test_end_state(self):
        from genesis_protocol.gluttony_os import get_self_knowledge
        sk = get_self_knowledge()
        response = sk.end_state_response()
        assert "GLUTTONY" in response
        assert "I observe" in response


class TestJournal:
    def test_write(self):
        from genesis_protocol.gluttony_os import get_journal
        j = get_journal()
        j.write("test", "Test entry")
        entries = j.get_entries()
        assert len(entries) > 0
    
    def test_observe(self):
        from genesis_protocol.gluttony_os import get_journal
        j = get_journal()
        j.observe("Test observation")
        entries = j.get_entries("observation")
        assert len(entries) > 0
    
    def test_learn(self):
        from genesis_protocol.gluttony_os import get_journal
        j = get_journal()
        j.learn("Test lesson")
        entries = j.get_entries("lesson")
        assert len(entries) > 0
    
    def test_summary(self):
        from genesis_protocol.gluttony_os import get_journal
        j = get_journal()
        summary = j.get_today_summary()
        assert "total_entries" in summary


class TestTrustBuilder:
    def test_record_action(self):
        from genesis_protocol.gluttony_os import get_trust_builder
        tb = get_trust_builder()
        tb.record_action("test", True)
        assert tb.successes > 0
    
    def test_reliability(self):
        from genesis_protocol.gluttony_os import get_trust_builder
        tb = get_trust_builder()
        tb.record_action("test", True)
        tb.record_action("test", True)
        tb.record_action("test", False)
        score = tb.get_reliability_score()
        assert 0.6 <= score <= 0.8
    
    def test_trust_level(self):
        from genesis_protocol.gluttony_os import get_trust_builder
        tb = get_trust_builder()
        tb.record_action("test", True)
        level = tb.get_trust_level()
        assert 0 <= level <= 1


class TestAutonomyController:
    def test_level(self):
        from genesis_protocol.gluttony_os import get_autonomy_controller
        ac = get_autonomy_controller()
        assert ac.get_level() == 0.3
    
    def test_forbidden(self):
        from genesis_protocol.gluttony_os import get_autonomy_controller
        ac = get_autonomy_controller()
        assert ac.can_execute("auto_deploy") is False
        assert ac.can_execute("spend_money") is False
    
    def test_increase_level(self):
        from genesis_protocol.gluttony_os import get_autonomy_controller
        ac = get_autonomy_controller()
        ac.increase_level()
        assert ac.get_level() > 0.3
    
    def test_status(self):
        from genesis_protocol.gluttony_os import get_autonomy_controller
        ac = get_autonomy_controller()
        status = ac.get_status()
        assert "level" in status
        assert "forbidden_gluttony_os" in status
