"""Tests for v1.9 Human Approval Layer"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestApprovalManager:
    def test_create_request(self):
        from genesis_protocol.approval import ApprovalManager
        mgr = ApprovalManager()
        req = mgr.create_request("P-1")
        assert req.proposal_id == "P-1"
        assert req.status.value == "pending"

    def test_approve(self):
        from genesis_protocol.approval import ApprovalManager
        mgr = ApprovalManager()
        req = mgr.create_request("P-1")
        mgr.approve(req.id, "Looks good")
        assert req.status.value == "approved"

    def test_reject(self):
        from genesis_protocol.approval import ApprovalManager
        mgr = ApprovalManager()
        req = mgr.create_request("P-1")
        mgr.reject(req.id, "Not needed")
        assert req.status.value == "rejected"

    def test_history(self):
        from genesis_protocol.approval import ApprovalManager
        mgr = ApprovalManager()
        mgr.create_request("P-1")
        history = mgr.get_history()
        assert "pending" in history


class TestFeedbackSystem:
    def test_add_feedback(self):
        from genesis_protocol.approval import FeedbackSystem
        fb = FeedbackSystem()
        result = fb.add_feedback("AR-1", "approved", "Looks good")
        assert result.decision == "approved"


class TestDecisionLearner:
    def test_record_approval(self):
        from genesis_protocol.approval import DecisionLearner
        learner = DecisionLearner()
        learner.record_approval("safe")
        assert learner.stats["approved"] == 1

    def test_preferred_risk(self):
        from genesis_protocol.approval import DecisionLearner
        learner = DecisionLearner()
        learner.record_approval("moderate")
        assert learner.get_preferred_risk_level() == "moderate"


class TestApprovalPolicies:
    def test_requires_approval(self):
        from genesis_protocol.approval import requires_approval
        assert requires_approval("safe") is True
        assert requires_approval("dangerous") is True


class TestNotificationSystem:
    def test_notify_approved(self):
        from genesis_protocol.approval import NotificationSystem
        ns = NotificationSystem()
        ns.notify_approved("P-1")
        assert len(ns.get_notifications()) == 1


class TestExplainability:
    def test_explain_proposal(self):
        from genesis_protocol.approval import ExplainabilityLayer
        expl = ExplainabilityLayer()
        proposal = {"problem": "Low memory", "risk_level": "safe", "confidence": 0.8, "evidence": []}
        explanation = expl.explain_proposal(proposal)
        assert "Why was this created?" in explanation
        assert "Low memory" in explanation
