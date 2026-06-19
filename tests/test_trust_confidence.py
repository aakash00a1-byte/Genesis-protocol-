"""Trust & Confidence System Tests - Genesis Protocol OMEGA

Tests for identity confidence levels:
- EXPLICIT: User directly stated
- OBSERVED: Available metadata/persisted records
- INFERRED: Derived from patterns/behavior
- UNKNOWN: No evidence exists
"""

import pytest
from genesis_protocol.ai.trust_confidence import (
    TrustConfidenceSystem,
    ConfidenceLevel,
    IdentityEvidence,
    get_trust_system
)
from datetime import datetime


class TestConfidenceLevels:
    """Test confidence level enum."""
    
    def test_explicit_level(self):
        """EXPLICIT: User directly stated."""
        assert ConfidenceLevel.EXPLICIT.value == "explicit"
    
    def test_observed_level(self):
        """OBSERVED: Available metadata/persisted records."""
        assert ConfidenceLevel.OBSERVED.value == "observed"
    
    def test_inferred_level(self):
        """INFERRED: Derived from patterns/behavior."""
        assert ConfidenceLevel.INFERRED.value == "inferred"
    
    def test_unknown_level(self):
        """UNKNOWN: No evidence exists."""
        assert ConfidenceLevel.UNKNOWN.value == "unknown"


class TestIdentityEvidence:
    """Test IdentityEvidence dataclass."""
    
    def test_create_evidence(self):
        """Create evidence with all fields."""
        evidence = IdentityEvidence(
            value="Aakash",
            confidence=ConfidenceLevel.EXPLICIT,
            source="user_stated",
            timestamp=datetime.utcnow()
        )
        
        assert evidence.value == "Aakash"
        assert evidence.confidence == ConfidenceLevel.EXPLICIT
        assert evidence.source == "user_stated"
    
    def test_evidence_with_raw_data(self):
        """Evidence with raw data."""
        evidence = IdentityEvidence(
            value="Aakash",
            confidence=ConfidenceLevel.OBSERVED,
            source="database",
            raw_data={"id": 123, "original": "aakash"}
        )
        
        assert evidence.raw_data["id"] == 123


class TestTrustConfidenceSystem:
    """Test TrustConfidenceSystem."""
    
    @pytest.fixture
    def trust_system(self):
        """Create fresh trust system for each test."""
        return TrustConfidenceSystem()
    
    # ============ Entity Identity Tests ============
    
    def test_entity_identity_explicit(self, trust_system):
        """Entity identity is ALWAYS EXPLICIT."""
        result = trust_system.get_entity_identity()
        
        assert result["status"] == "explicit"
        assert result["confidence"] == "explicit"
        assert result["data"]["name"] == "GLUTTONY"
        assert result["data"]["nickname"] == "Gluten"
        assert result["source"] == "hardcoded_entity_definition"
    
    def test_entity_identity_no_qualification(self, trust_system):
        """Entity identity needs no qualification - state confidently."""
        result = trust_system.get_entity_identity()
        
        # EXPLICIT → no message qualification needed
        assert result["message"] is None
    
    # ============ User Identity Tests ============
    
    def test_user_identity_unknown_no_user_id(self, trust_system):
        """Unknown when no user_id provided."""
        result = trust_system.get_user_identity(user_id=None)
        
        assert result["status"] == "unknown"
        assert result["confidence"] == "unknown"
        assert result["data"] is None
        # UNKNOWN → asks user
        assert "Could you please tell me" in result["message"]
    
    def test_user_identity_unknown_no_evidence(self, trust_system):
        """Unknown when no evidence exists."""
        result = trust_system.get_user_identity(user_id=99999)
        
        assert result["status"] == "unknown"
        assert "Could you please tell me" in result["message"]
    
    def test_store_and_retrieve_explicit(self, trust_system):
        """Store EXPLICIT identity and retrieve."""
        trust_system.store_user_identity(
            user_id=1,
            field="name",
            value="Aakash",
            confidence=ConfidenceLevel.EXPLICIT,
            source="user_stated"
        )
        
        evidence = trust_system.get_evidence(1, "name")
        
        assert evidence is not None
        assert evidence.value == "Aakash"
        assert evidence.confidence == ConfidenceLevel.EXPLICIT
        assert evidence.source == "user_stated"
    
    def test_store_and_retrieve_observed(self, trust_system):
        """Store OBSERVED identity and retrieve."""
        trust_system.store_user_identity(
            user_id=2,
            field="email",
            value="aakash@example.com",
            confidence=ConfidenceLevel.OBSERVED,
            source="metadata"
        )
        
        evidence = trust_system.get_evidence(2, "email")
        
        assert evidence is not None
        assert evidence.value == "aakash@example.com"
        assert evidence.confidence == ConfidenceLevel.OBSERVED
    
    def test_store_and_retrieve_inferred(self, trust_system):
        """Store INFERRED identity and retrieve."""
        trust_system.store_user_identity(
            user_id=3,
            field="name",
            value="Aakash",
            confidence=ConfidenceLevel.INFERRED,
            source="conversation_pattern"
        )
        
        evidence = trust_system.get_evidence(3, "name")
        
        assert evidence is not None
        assert evidence.value == "Aakash"
        assert evidence.confidence == ConfidenceLevel.INFERRED
    
    # ============ Response Formatting Tests ============
    
    def test_explicit_response_format(self, trust_system):
        """EXPLICIT → state confidently."""
        trust_system.store_user_identity(
            user_id=10,
            field="name",
            value="Aakash",
            confidence=ConfidenceLevel.EXPLICIT,
            source="user_stated"
        )
        
        evidence = trust_system._format_with_confidence(
            IdentityEvidence(
                value="Aakash",
                confidence=ConfidenceLevel.EXPLICIT,
                source="user_stated"
            ),
            "name"
        )
        
        # EXPLICIT → no qualification
        assert evidence["message"] is None
        assert evidence["data"] == "Aakash"
    
    def test_observed_response_format(self, trust_system):
        """OBSERVED → say 'Available records indicate...'."""
        evidence = trust_system._format_with_confidence(
            IdentityEvidence(
                value="Aakash",
                confidence=ConfidenceLevel.OBSERVED,
                source="database"
            ),
            "name"
        )
        
        # OBSERVED → qualification message
        assert "Available records indicate" in evidence["message"]
        assert "may be" in evidence["message"]
        assert evidence["data"] == "Aakash"
    
    def test_inferred_response_format(self, trust_system):
        """INFERRED → say 'I suspect..., but I am not certain.'"""
        evidence = trust_system._format_with_confidence(
            IdentityEvidence(
                value="Aakash",
                confidence=ConfidenceLevel.INFERRED,
                source="pattern"
            ),
            "name"
        )
        
        # INFERRED → uncertainty message
        assert "I suspect" in evidence["message"]
        assert "I am not certain" in evidence["message"]
        assert evidence["data"] == "Aakash"
    
    def test_unknown_response_format(self, trust_system):
        """UNKNOWN → ask user instead of guessing."""
        result = trust_system._unknown_response("name")
        
        assert result["status"] == "unknown"
        assert "Could you please tell me" in result["message"]
        assert result["data"] is None
    
    # ============ Query Building Tests ============
    
    def test_build_query_for_unknown(self, trust_system):
        """Build query when unknown - asks user."""
        query = trust_system.build_identity_query("your", "name")
        
        assert "Could you please tell me" in query
    
    def test_build_query_for_explicit(self, trust_system):
        """Build query when known - states fact."""
        trust_system.store_user_identity(
            user_id=20,
            field="name",
            value="Test",
            confidence=ConfidenceLevel.EXPLICIT,
            source="test"
        )
        
        # This would query for the stored user
        # (Note: need proper user context)
    
    # ============ Statistics Tests ============
    
    def test_confidence_stats_empty(self, trust_system):
        """Stats when no evidence."""
        stats = trust_system.get_confidence_stats()
        
        assert stats["total"] == 0
        assert stats["by_confidence"] == {}
    
    def test_confidence_stats_with_data(self, trust_system):
        """Stats with evidence."""
        trust_system.store_user_identity(
            user_id=30,
            field="name",
            value="Aakash",
            confidence=ConfidenceLevel.EXPLICIT,
            source="test"
        )
        trust_system.store_user_identity(
            user_id=30,
            field="email",
            value="test@test.com",
            confidence=ConfidenceLevel.OBSERVED,
            source="test"
        )
        
        stats = trust_system.get_confidence_stats()
        
        assert stats["total"] == 2
        assert stats["by_confidence"]["explicit"] == 1
        assert stats["by_confidence"]["observed"] == 1
    
    # ============ All Evidence Tests ============
    
    def test_get_all_evidence(self, trust_system):
        """Get all evidence for a user."""
        trust_system.store_user_identity(
            user_id=40,
            field="name",
            value="Aakash",
            confidence=ConfidenceLevel.EXPLICIT,
            source="test"
        )
        trust_system.store_user_identity(
            user_id=40,
            field="city",
            value="Delhi",
            confidence=ConfidenceLevel.INFERRED,
            source="test"
        )
        
        all_evidence = trust_system.get_all_evidence(40)
        
        assert "name" in all_evidence
        assert "city" in all_evidence
        assert all_evidence["name"].confidence == ConfidenceLevel.EXPLICIT
        assert all_evidence["city"].confidence == ConfidenceLevel.INFERRED


class TestConfidenceRules:
    """Test that confidence rules are followed."""
    
    def test_never_promote_inference_to_fact(self):
        """INFERRED should never be stated as fact."""
        trust = TrustConfidenceSystem()
        
        result = trust._format_with_confidence(
            IdentityEvidence(
                value="GuessedName",
                confidence=ConfidenceLevel.INFERRED,
                source="pattern"
            ),
            "name"
        )
        
        # Should have uncertainty language
        assert "I suspect" in result["message"] or "may be" in result["message"]
        # Should NOT state as fact
        assert result["message"] is not None  # Has qualification
    
    def test_unknown_asks_user(self):
        """UNKNOWN should ask user, not guess."""
        trust = TrustConfidenceSystem()
        
        result = trust._unknown_response("name")
        
        assert "Could you please tell me" in result["message"]
        # Should not provide any value
        assert result["data"] is None
    
    def test_explicit_states_confidently(self):
        """EXPLICIT should state without qualification."""
        trust = TrustConfidenceSystem()
        
        result = trust._format_with_confidence(
            IdentityEvidence(
                value="Aakash",
                confidence=ConfidenceLevel.EXPLICIT,
                source="user_stated"
            ),
            "name"
        )
        
        # No message qualification needed
        assert result["message"] is None
        assert result["data"] == "Aakash"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
