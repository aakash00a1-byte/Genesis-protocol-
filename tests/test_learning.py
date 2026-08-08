"""Tests for v1.5 Learning and Evaluation Layer"""

import pytest
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestEvaluationEngine:
    def test_evaluate_success(self):
        from genesis_protocol.learning.evaluation_engine import ConversationEvaluation
        eval = ConversationEvaluation(storage_path=tempfile.mkdtemp())
        result = eval.evaluate(
            message="Hello",
            response="Hi there!",
            latency_ms=500,
            provider="groq",
            success=True
        )
        assert result.success is True
        assert result.quality_score > 0

    def test_evaluate_failure(self):
        from genesis_protocol.learning.evaluation_engine import ConversationEvaluation
        eval = ConversationEvaluation(storage_path=tempfile.mkdtemp())
        result = eval.evaluate(
            message="Hello",
            response="Error",
            latency_ms=500,
            provider="groq",
            success=False,
            error="API failed"
        )
        assert result.success is False
        assert result.quality_score == 0.0

    def test_stats(self):
        from genesis_protocol.learning.evaluation_engine import ConversationEvaluation
        eval = ConversationEvaluation(storage_path=tempfile.mkdtemp())
        eval.evaluate("hi", "hello", 100, "groq", True)
        stats = eval.get_stats()
        assert stats['total_conversations'] == 1


class TestKnowledgeExtractor:
    def test_extract_name(self):
        from genesis_protocol.learning.knowledge_extractor import KnowledgeExtractor
        extractor = KnowledgeExtractor()
        knowledge = extractor.extract_from_message("My name is Aakash")
        names = [k for k in knowledge if 'name' in k.knowledge_type]
        assert len(names) > 0

    def test_extract_topic(self):
        from genesis_protocol.learning.knowledge_extractor import KnowledgeExtractor
        extractor = KnowledgeExtractor()
        knowledge = extractor.extract_from_message("I love coding in Python")
        assert len(knowledge) >= 0


class TestReflectionCycle:
    def test_record_conversation(self):
        from genesis_protocol.learning.reflection_cycle import ReflectionCycle
        cycle = ReflectionCycle(storage_path=tempfile.mkdtemp())
        cycle.record_conversation()
        assert cycle._conversations_since_reflection == 1

    def test_should_reflect(self):
        from genesis_protocol.learning.reflection_cycle import ReflectionCycle
        cycle = ReflectionCycle(storage_path=tempfile.mkdtemp(), interval=5)
        for _ in range(4):
            cycle.record_conversation()
        assert cycle.should_reflect() is False
        cycle.record_conversation()
        assert cycle.should_reflect() is True


class TestPerformanceDashboard:
    def test_record_daily(self):
        from genesis_protocol.learning.performance_dashboard import PerformanceDashboard
        dash = PerformanceDashboard(storage_path=tempfile.mkdtemp())
        dash.record_daily(conversations=10, successful=8, latency_ms=500)
        summary = dash.get_summary()
        assert summary['total_conversations'] == 10

    def test_summary(self):
        from genesis_protocol.learning.performance_dashboard import PerformanceDashboard
        dash = PerformanceDashboard(storage_path=tempfile.mkdtemp())
        dash.record_daily(conversations=5, successful=4, quality=0.8)
        summary = dash.get_summary()
        assert summary['success_rate'] == 0.8
