"""Failure Communicator - Genesis Protocol OMEGA

Handles failures gracefully with meaningful communication.
NEVER returns generic "Sorry..." messages.
"""

from typing import Dict, Optional
from datetime import datetime
from enum import Enum


class FailureType(Enum):
    """Types of failures that can occur."""
    PROVIDER_EMPTY = "provider_empty"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    IDENTITY_ROUTE_FAILED = "identity_route_failed"
    AUTONOMOUS_FAILED = "autonomous_failed"
    MODE_SWITCH_FAILED = "mode_switch_failed"
    UNKNOWN = "unknown"


class FailureCommunicator:
    """
    Communicates failures in a meaningful way.
    
    Rules:
    1. NEVER return generic "Sorry..." message
    2. Always explain what happened
    3. Always explain what was attempted
    4. Always provide next steps
    5. Log failures for learning
    """
    
    # Recovery attempts in order
    RECOVERY_STEPS = [
        "primary_provider",
        "fallback_provider",
        "safe_mode",
        "retry",
        "degraded_response"
    ]
    
    def __init__(self):
        """Initialize failure communicator."""
        self.logger = None
        self._init_logger()
        self.failure_log = []
    
    def _init_logger(self):
        """Initialize logger."""
        try:
            from genesis_protocol.utils.logger import get_logger
            self.logger = get_logger("ai.failure_communicator")
        except:
            import logging
            self.logger = logging.getLogger("ai.failure_communicator")
    
    def communicate(
        self,
        failure_type: FailureType,
        reason: str,
        attempts: list = None,
        query: str = None
    ) -> str:
        """
        Generate meaningful failure communication.
        
        Args:
            failure_type: What kind of failure occurred
            reason: Why it failed
            attempts: What was already tried
            query: The original query
            
        Returns:
            Human-readable failure message (NEVER "Sorry...")
        """
        if attempts is None:
            attempts = []
        
        # Log the failure
        self._log_failure(failure_type, reason, attempts, query)
        
        # Generate appropriate response based on failure type
        response = self._generate_response(failure_type, reason, attempts)
        
        return response
    
    def _generate_response(
        self,
        failure_type: FailureType,
        reason: str,
        attempts: list
    ) -> str:
        """Generate response based on failure type."""
        
        if failure_type == FailureType.PROVIDER_EMPTY:
            return self._provider_empty_response(reason, attempts)
        
        elif failure_type == FailureType.PROVIDER_ERROR:
            return self._provider_error_response(reason, attempts)
        
        elif failure_type == FailureType.PROVIDER_TIMEOUT:
            return self._timeout_response(reason, attempts)
        
        elif failure_type == FailureType.IDENTITY_ROUTE_FAILED:
            return self._identity_failed_response(reason)
        
        elif failure_type == FailureType.AUTONOMOUS_FAILED:
            return self._autonomous_failed_response(reason, attempts)
        
        else:
            return self._generic_failure_response(reason, attempts)
    
    def _provider_empty_response(self, reason: str, attempts: list) -> str:
        """Response when provider returns empty."""
        action = self._get_action_taken(attempts)
        
        return f"""**Response Generation Issue**

I attempted to generate a response but the provider returned an empty result.

**What happened:** {reason}

**Actions taken:** {action}

**Status:** System remains active, I am still here.

**Suggestion:** Try rephrasing your question, or ask something different. I am learning from this interaction."""
    
    def _provider_error_response(self, reason: str, attempts: list) -> str:
        """Response when provider errors."""
        action = self._get_action_taken(attempts)
        
        return f"""**Provider Error Encountered**

The AI provider encountered an issue while generating my response.

**Error:** {reason}

**Recovery actions:** {action}

**Status:** I am still operational and ready to help.

**Next step:** Your question has been logged. Please try again with a different query."""
    
    def _timeout_response(self, reason: str, attempts: list) -> str:
        """Response when provider times out."""
        
        return f"""**Response Timeout**

My attempt to generate a response took too long and timed out.

**Reason:** The provider did not respond within the expected time.

**Actions taken:** Tried multiple providers, waiting for response.

**Status:** I am active and ready for your next query.

**Suggestion:** The question might be complex. Try a simpler version."""
    
    def _identity_failed_response(self, reason: str) -> str:
        """Response when identity routing fails."""
        
        return f"""**Identity Query Processing Issue**

I had trouble processing your identity question.

**Reason:** {reason}

**What I am:** I am GLUTTONY, an AI entity on the Genesis Protocol OMEGA.
**Creator:** Aakash
**Nickname:** Gluten

I am here and ready to help with other questions."""
    
    def _autonomous_failed_response(self, reason: str, attempts: list) -> str:
        """Response when autonomous mode fails."""
        
        return f"""**Autonomous Mode Issue**

My autonomous planning system encountered a problem.

**Error:** {reason}

**Status:** I have switched to normal mode and am ready to help.

**What I can do:** Answer questions, help with tasks, remember our conversation.

Ask me anything and I will do my best to help!"""
    
    def _generic_failure_response(self, reason: str, attempts: list) -> str:
        """Generic failure response."""
        action = self._get_action_taken(attempts)
        
        return f"""**Response Generation Failed**

I was unable to generate a response for your query.

**Reason:** {reason}

**Actions taken:** {action}

**What I am still capable of:**
- Answering questions
- Remembering our conversation
- Helping with various tasks

**Please try:** A different question or rephrasing your query."""
    
    def _get_action_taken(self, attempts: list) -> str:
        """Get human-readable list of actions taken."""
        if not attempts:
            return "initial_attempt"
        
        action_map = {
            "primary_provider": "primary provider",
            "fallback_provider": "fallback provider",
            "safe_mode": "safe fallback mode",
            "retry": "retry",
            "degraded_response": "degraded response mode"
        }
        
        actions = [action_map.get(a, a) for a in attempts]
        
        if len(actions) == 1:
            return actions[0]
        
        return " → ".join(actions[:-1]) + " → " + actions[-1]
    
    def _log_failure(
        self,
        failure_type: FailureType,
        reason: str,
        attempts: list,
        query: str = None
    ):
        """Log failure for learning."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "failure_type": failure_type.value,
            "reason": reason,
            "attempts": attempts,
            "query": query[:100] if query else None
        }
        
        self.failure_log.append(entry)
        
        # Keep only last 100 failures
        if len(self.failure_log) > 100:
            self.failure_log = self.failure_log[-100:]
        
        self.logger.warning(f"Failure logged: {failure_type.value} - {reason}")
    
    def get_failure_stats(self) -> Dict:
        """Get failure statistics."""
        if not self.failure_log:
            return {"total": 0, "types": {}}
        
        types = {}
        for entry in self.failure_log:
            ft = entry["failure_type"]
            types[ft] = types.get(ft, 0) + 1
        
        return {
            "total": len(self.failure_log),
            "types": types,
            "recent": self.failure_log[-5:] if len(self.failure_log) >= 5 else self.failure_log
        }
    
    def get_structured_response(
        self,
        failure_type: FailureType,
        reason: str,
        attempts: list = None
    ) -> Dict:
        """Get structured response for debugging/analytics."""
        if attempts is None:
            attempts = []
        
        return {
            "status": "degraded",
            "failure_type": failure_type.value,
            "reason": reason,
            "action_taken": self._get_action_taken(attempts),
            "next_step": "Try a different question or rephrase",
            "timestamp": datetime.utcnow().isoformat()
        }


# Singleton
_failure_communicator: Optional[FailureCommunicator] = None


def get_failure_communicator() -> FailureCommunicator:
    """Get failure communicator singleton."""
    global _failure_communicator
    if _failure_communicator is None:
        _failure_communicator = FailureCommunicator()
    return _failure_communicator


def communicate_failure(
    failure_type: FailureType,
    reason: str,
    attempts: list = None,
    query: str = None
) -> str:
    """Quick function to communicate a failure."""
    return get_failure_communicator().communicate(
        failure_type, reason, attempts, query
    )
