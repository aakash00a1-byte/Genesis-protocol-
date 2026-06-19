"""Tests for v1.8 Proposal Engine"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestProposalManager:
    def test_create_proposal(self):
        from genesis_protocol.proposal import ProposalManager, ProposalCategory
        mgr = ProposalManager()
        p = mgr.create_proposal(
            "Memory recall improvement",
            "Recall is 73%",
            "Improve summarization",
            ProposalCategory.MEMORY,
            "safe",
            0.85
        )
        assert p.id.startswith("P-")
        assert p.status.value == "draft"

    def test_workflow(self):
        from genesis_protocol.proposal import ProposalManager, ProposalCategory
        mgr = ProposalManager()
        p = mgr.create_proposal("Test", "Problem", "Solution", ProposalCategory.BUG, "safe", 0.8)
        mgr.submit_for_review(p.id)
        assert p.status.value == "review"
        mgr.approve(p.id)
        assert p.status.value == "approved"

    def test_history(self):
        from genesis_protocol.proposal import ProposalManager, ProposalCategory
        mgr = ProposalManager()
        mgr.create_proposal("T1", "P1", "S1", ProposalCategory.BUG, "safe", 0.8)
        mgr.create_proposal("T2", "P2", "S2", ProposalCategory.MEMORY, "moderate", 0.7)
        history = mgr.get_history()
        assert history["total"] >= 2


class TestEvidenceCollector:
    def test_collect_metrics(self):
        from genesis_protocol.proposal import EvidenceCollector
        collector = EvidenceCollector()
        evidence = collector.collect_metrics({"accuracy": 0.73})
        assert evidence["type"] == "metrics"
        assert evidence["data"]["accuracy"] == 0.73

    def test_collect_error(self):
        from genesis_protocol.proposal import EvidenceCollector
        collector = EvidenceCollector()
        evidence = collector.collect_error("Null pointer", "API call")
        assert evidence["type"] == "error"
        assert evidence["error"] == "Null pointer"


class TestConfidenceEngine:
    def test_compute_confidence(self):
        from genesis_protocol.proposal import ConfidenceEngine
        engine = ConfidenceEngine()
        result = engine.compute_confidence(
            [{"type": "metrics"}],
            "safe",
            0.8
        )
        assert "confidence" in result
        assert result["confidence"] > 0.5


class TestProposalRanker:
    def test_rank(self):
        from genesis_protocol.proposal import ProposalRanker
        ranker = ProposalRanker()
        proposals = [
            {"confidence": 0.9, "risk_level": "safe", "estimated_impact": "high", "importance": 0.8},
            {"confidence": 0.5, "risk_level": "dangerous", "estimated_impact": "low", "importance": 0.3}
        ]
        ranked = ranker.rank(proposals)
        assert ranked[0]["rank_score"] > ranked[1]["rank_score"]

    def test_top_proposals(self):
        from genesis_protocol.proposal import ProposalRanker
        ranker = ProposalRanker()
        proposals = [
            {"confidence": 0.9, "risk_level": "safe", "estimated_impact": "high", "importance": 0.8},
            {"confidence": 0.7, "risk_level": "moderate", "estimated_impact": "medium", "importance": 0.6},
            {"confidence": 0.5, "risk_level": "dangerous", "estimated_impact": "low", "importance": 0.3}
        ]
        top = ranker.get_top_proposals(proposals, 2)
        assert len(top) == 2
