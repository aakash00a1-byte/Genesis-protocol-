"""Trust & Identity Confidence System - Genesis Protocol OS

Manages confidence levels for identity claims.
Never promotes inference into fact.

Confidence Levels:
- EXPLICIT: User directly stated
- OBSERVED: Available metadata/persisted records
- INFERRED: Derived from patterns/behavior
- UNKNOWN: No evidence exists
"""

from typing import Optional, Dict, List
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field


class ConfidenceLevel(Enum):
    """Identity confidence levels."""
    EXPLICIT = "explicit"      # User directly stated
    OBSERVED = "observed"      # Metadata/persisted records
    INFERRED = "inferred"      # Derived from patterns
    UNKNOWN = "unknown"        # No evidence


@dataclass
class IdentityEvidence:
    """Evidence for an identity claim."""
    value: str
    confidence: ConfidenceLevel
    source: str                    # Where this came from
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_data: Optional[Dict] = None  # Original data if needed


class TrustConfidenceSystem:
    """
    Manages identity claims with proper confidence levels.
    
    Rules:
    1. EXPLICIT → state confidently
    2. OBSERVED → say "Available records indicate..."
    3. INFERRED → say "I suspect..., but I am not certain."
    4. UNKNOWN → ask the user instead of guessing
    """
    
    def __init__(self):
        """Initialize trust & confidence system."""
        self.logger = None
        self._init_logger()
        self._identity_cache: Dict[str, IdentityEvidence] = {}
    
    def _init_logger(self):
        """Initialize logger."""
        try:
            from genesis_protocol.utils.logger import get_logger
            self.logger = get_logger("ai.trust_confidence")
        except Exception:
            import logging
            self.logger = logging.getLogger("ai.trust_confidence")
    
    # ============ Entity Identity ============
    
    def get_entity_identity(self) -> Dict:
        """
        Get entity identity with EXPLICIT confidence.
        Entity identity is ALWAYS explicit - hardcoded.
        """
        return {
            "status": "explicit",
            "confidence": ConfidenceLevel.EXPLICIT.value,
            "data": {
                "name": "GLUTTONY",
                "nickname": "Gluten",
                "variant": "OS",
                "creator": "Aakash",
                "protocol_version": "OS"
            },
            "source": "hardcoded_entity_definition",
            "message": None  # No qualification needed
        }
    
    # ============ User Identity ============
    
    def get_user_identity(self, user_id: int = None) -> Dict:
        """
        Get user identity with proper confidence.
        """
        evidence = self._get_user_evidence(user_id)
        
        if evidence is None:
            return self._unknown_response("your name")
        
        return self._format_with_confidence(evidence, "your name")
    
    def _get_user_evidence(self, user_id: int = None) -> Optional[IdentityEvidence]:
        """
        Get user identity evidence from memory.
        """
        if user_id is None:
            return None
        
        # Try to get from memory
        try:
            from genesis_protocol.memory.unified_memory import get_unified_memory
            
            memory = get_unified_memory()
            context = memory.get_context(user_id, "")
            
            # Check for name in context
            if context:
                # Look for patterns like "name is X" or "I'm X"
                import re
                patterns = [
                    r"(?:name is|my name is|i'm|i am|naam hai)\s+([A-Za-z]+)",
                    r"(?:user.*name|named|called)\s+([A-Za-z]+)"
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, context, re.IGNORECASE)
                    if match:
                        return IdentityEvidence(
                            value=match.group(1).title(),
                            confidence=ConfidenceLevel.INFERRED,
                            source="context_pattern_analysis"
                        )
        except Exception:
            pass
        
        return None
    
    def _format_with_confidence(self, evidence: IdentityEvidence, subject: str) -> Dict:
        """Format identity claim with proper confidence messaging."""
        
        if evidence.confidence == ConfidenceLevel.EXPLICIT:
            return {
                "status": "explicit",
                "confidence": evidence.confidence.value,
                "data": evidence.value,
                "source": evidence.source,
                "message": None  # Can state confidently
            }
        
        elif evidence.confidence == ConfidenceLevel.OBSERVED:
            return {
                "status": "observed",
                "confidence": evidence.confidence.value,
                "data": evidence.value,
                "source": evidence.source,
                "message": f"Available records indicate your {subject} may be {evidence.value}, but I do not have explicit confirmation."
            }
        
        elif evidence.confidence == ConfidenceLevel.INFERRED:
            return {
                "status": "inferred",
                "confidence": evidence.confidence.value,
                "data": evidence.value,
                "source": evidence.source,
                "message": f"I suspect your {subject} may be {evidence.value}, but I am not certain. Please confirm if this is correct."
            }
        
        else:  # UNKNOWN
            return self._unknown_response(subject)
    
    def _unknown_response(self, subject: str) -> Dict:
        """Return unknown response - asks user instead of guessing."""
        return {
            "status": "unknown",
            "confidence": ConfidenceLevel.UNKNOWN.value,
            "data": None,
            "source": "none",
            "message": f"I do not know {subject}. Could you please tell me?"
        }
    
    # ============ Store User Identity ============
    
    def store_user_identity(
        self,
        user_id: int,
        field: str,
        value: str,
        confidence: ConfidenceLevel,
        source: str
    ) -> bool:
        """
        Store user identity with evidence.
        
        Args:
            user_id: User ID
            field: Field name (name, email, etc.)
            value: The value
            confidence: How we know this
            source: Where this came from (user_stated, metadata, pattern)
        """
        key = f"{user_id}:{field}"
        
        evidence = IdentityEvidence(
            value=value,
            confidence=confidence,
            source=source,
            timestamp=datetime.utcnow()
        )
        
        self._identity_cache[key] = evidence
        
        # Also try to store in memory
        try:
            from genesis_protocol.memory.unified_memory import get_unified_memory
            memory = get_unified_memory()
            
            # Store with metadata
            memory_key = f"user:{user_id}:identity:{field}"
            memory.store_interaction(
                user_id, user_id,
                f"{field}:{value}",
                f"confidence:{confidence.value},source:{source}",
                "identity"
            )
        except Exception as e:
            self.logger.warning(f"Could not store in memory: {e}")
        
        self.logger.info(f"Stored identity {field}={value} for user {user_id} ({confidence.value})")
        return True
    
    # ============ Query Building ============
    
    def build_identity_query(self, subject: str, field: str) -> str:
        """
        Build a proper identity query with confidence.
        
        Example:
            build_identity_query("your", "name")
            → "What is your name?"
        
        For unknown fields:
            → "I do not know your X. Could you tell me?"
        """
        evidence_key = f"user:{field}"
        
        if evidence_key in self._identity_cache:
            evidence = self._identity_cache[evidence_key]
            return self._format_query_message(evidence, field)
        
        return f"I do not know your {field}. Could you please tell me?"
    
    def _format_query_message(self, evidence: IdentityEvidence, field: str) -> str:
        """Format message for known identity."""
        
        if evidence.confidence == ConfidenceLevel.EXPLICIT:
            return f"Your {field} is {evidence.value}."
        
        elif evidence.confidence == ConfidenceLevel.OBSERVED:
            return f"Available records indicate your {field} may be {evidence.value}."
        
        elif evidence.confidence == ConfidenceLevel.INFERRED:
            return f"I suspect your {field} may be {evidence.value}, but I'm not certain. Is this correct?"
        
        else:
            return f"I do not know your {field}. Could you please tell me?"
    
    # ============ Evidence Access ============
    
    def get_evidence(self, user_id: int, field: str) -> Optional[IdentityEvidence]:
        """Get evidence for a user identity field."""
        key = f"{user_id}:{field}"
        return self._identity_cache.get(key)
    
    def get_all_evidence(self, user_id: int) -> Dict[str, IdentityEvidence]:
        """Get all evidence for a user."""
        prefix = f"{user_id}:"
        return {
            k.replace(prefix, ""): v 
            for k, v in self._identity_cache.items() 
            if k.startswith(prefix)
        }
    
    def get_confidence_stats(self) -> Dict:
        """Get statistics on stored evidence."""
        stats = {
            "total": len(self._identity_cache),
            "by_confidence": {},
            "recent": []
        }
        
        for evidence in self._identity_cache.values():
            conf = evidence.confidence.value
            stats["by_confidence"][conf] = stats["by_confidence"].get(conf, 0) + 1
        
        # Recent 5
        sorted_evidence = sorted(
            self._identity_cache.items(),
            key=lambda x: x[1].timestamp,
            reverse=True
        )
        stats["recent"] = [
            {"key": k, "value": v.value, "confidence": v.confidence.value}
            for k, v in sorted_evidence[:5]
        ]
        
        return stats


# Singleton
_trust_system: Optional[TrustConfidenceSystem] = None


def get_trust_system() -> TrustConfidenceSystem:
    """Get trust & confidence system singleton."""
    global _trust_system
    if _trust_system is None:
        _trust_system = TrustConfidenceSystem()
    return _trust_system


# Convenience functions
def get_user_identity_confidence(user_id: int = None) -> Dict:
    """Get user identity with confidence."""
    return get_trust_system().get_user_identity(user_id)


def store_identity_evidence(
    user_id: int,
    field: str,
    value: str,
    confidence: str = "inferred",
    source: str = "unknown"
) -> bool:
    """Store identity evidence."""
    conf_level = ConfidenceLevel(confidence)
    return get_trust_system().store_user_identity(
        user_id, field, value, conf_level, source
    )
