"""Tests for v1.7 Safe Self-Improvement Layer"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWeaknessDetector:
    def test_detect_weakness(self):
        from genesis_protocol.improvement import WeaknessDetector, WeaknessType
        detector = WeaknessDetector()
        weak = detector.detect_weakness(
            WeaknessType.MEMORY_RECALL,
            "Low memory recall",
            ["Evidence 1"],
            0.7
        )
        assert weak.severity == 0.7
        assert weak.status == "active"

    def test_get_summary(self):
        from genesis_protocol.improvement import WeaknessDetector, WeaknessType
        detector = WeaknessDetector()
        detector.detect_weakness(WeaknessType.CODING_ACCURACY, "Issue", [], 0.5)
        summary = detector.get_summary()
        assert "total_weaknesses" in summary


class TestSafetyRules:
    def test_forbidden_actions(self):
        from genesis_protocol.improvement import SafetyRules
        rules = SafetyRules()
        assert rules.is_allowed("auto_deploy") is False
        assert rules.is_allowed("safe_action") is True

    def test_requires_approval(self):
        from genesis_protocol.improvement import SafetyRules
        rules = SafetyRules()
        assert rules.requires_approval("modify_core") is True
        assert rules.requires_approval("safe_action") is False

    def test_status(self):
        from genesis_protocol.improvement import SafetyRules
        rules = SafetyRules()
        status = rules.get_status()
        assert status["enabled"] is True


class TestRiskEngine:
    def test_safe_assessment(self):
        from genesis_protocol.improvement import RiskEngine
        engine = RiskEngine()
        result = engine.assess_risk({
            "proposed_solution": "Add test for edge case",
            "files_affected": ["tests/test_example.py"]
        })
        assert result["risk_level"] in ["safe", "moderate"]

    def test_dangerous_assessment(self):
        from genesis_protocol.improvement import RiskEngine
        engine = RiskEngine()
        result = engine.assess_risk({
            "proposed_solution": "Use eval() for dynamic code",
            "files_affected": ["core/handler.py"]
        })
        assert result["risk_level"] == "dangerous"


class TestPatchProposal:
    def test_generate_proposal(self):
        from genesis_protocol.improvement import ProposalGenerator, RiskLevel
        gen = ProposalGenerator()
        proposal = gen.generate_proposal(
            problem="Memory recall low",
            evidence=["Evidence 1"],
            proposed_solution="Improve summarization",
            risk_level=RiskLevel.SAFE,
            confidence=0.8
        )
        assert proposal.risk_level == RiskLevel.SAFE
        assert proposal.status.value == "draft"

    def test_workflow(self):
        from genesis_protocol.improvement import ProposalGenerator, RiskLevel
        gen = ProposalGenerator()
        proposal = gen.generate_proposal(
            "Problem", [], "Solution", RiskLevel.SAFE, 0.7
        )
        gen.propose(proposal.id)
        assert proposal.status.value == "proposed"


class TestSimulationLayer:
    def test_simulate(self):
        from genesis_protocol.improvement import SimulationLayer
        sim = SimulationLayer()
        result = sim.simulate({
            "proposed_solution": "Add better tests",
            "problem": "Coverage low"
        })
        assert result.success is True


class TestImprovementAnalyzer:
    def test_analyze_failures(self):
        from genesis_protocol.improvement import ImprovementAnalyzer
        analyzer = ImprovementAnalyzer()
        opportunities = analyzer.analyze_failures({
            "success_rate": 0.5,
            "average_latency_ms": 5000
        })
        assert len(opportunities) >= 1
