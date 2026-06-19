"""GLUTTONY Core - Genesis Protocol v3.0

The unified entity that ties all layers together."""

from typing import Dict, List, Optional, Any
from datetime import datetime


class GluttonyEntity:
    """The GLUTTONY AI Entity."""
    
    def __init__(self, name: str = "GLUTTONY"):
        self.name = name
        self.version = "3.0"
        self.created_at = datetime.now()
        self.last_active = datetime.now()
        self._init_layers()
    
    def _init_layers(self):
        """Initialize all Genesis Protocol layers."""
        # v1.3: Autonomous Layer
        try:
            from genesis_protocol.autonomous import get_autonomous_daemon
            self.autonomous = get_autonomous_daemon()
        except:
            self.autonomous = None
        
        # v1.4: Interaction Layer
        try:
            from genesis_protocol.interaction import get_context_manager
            self.context = get_context_manager()
        except:
            self.context = None
        
        # v1.5: Learning Layer
        try:
            from genesis_protocol.learning import get_evaluation_engine
            self.learning = get_evaluation_engine()
        except:
            self.learning = None
        
        # v1.6: Tools
        try:
            from genesis_protocol.tools import get_tool_registry
            self.tools = get_tool_registry()
        except:
            self.tools = None
        
        # v1.7: Improvement
        try:
            from genesis_protocol.improvement import get_weakness_detector
            self.improvement = get_weakness_detector()
        except:
            self.improvement = None
        
        # v1.8: Proposal
        try:
            from genesis_protocol.proposal import get_proposal_manager
            self.proposals = get_proposal_manager()
        except:
            self.proposals = None
        
        # v1.9: Approval
        try:
            from genesis_protocol.approval import get_approval_manager
            self.approval = get_approval_manager()
        except:
            self.approval = None
        
        # v3.0: Survival Layer
        try:
            from genesis_protocol.survival import get_survival_manager
            self.survival = get_survival_manager()
        except:
            self.survival = None
    
    def think(self, message: str, context: Dict = None) -> Dict:
        """Process a message and generate response."""
        self.last_active = datetime.now()
        
        response = {
            "entity": self.name,
            "version": self.version,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "layers_active": self._get_active_layers(),
            "response": f"I am {self.name}, version {self.version}"
        }
        
        if self.proposals:
            history = self.proposals.get_history()
            response["proposals"] = history
        
        if self.approval:
            response["approval_queue"] = len(self.approval.get_pending())
        
        if self.survival:
            response["survival_status"] = self.survival.get_full_status()
        
        return response
    
    def observe(self) -> Dict:
        """Self-observe current state."""
        obs = {
            "name": self.name,
            "version": self.version,
            "uptime": str(datetime.now() - self.created_at),
            "last_active": self.last_active.isoformat(),
            "layers": self._get_active_layers()
        }
        
        if self.survival:
            obs["survival"] = self.survival.get_full_status()
        
        return obs
    
    def _get_active_layers(self) -> List[str]:
        """Get list of active layers."""
        layers = []
        if self.autonomous:
            layers.append("v1.3-autonomous")
        if self.context:
            layers.append("v1.4-interaction")
        if self.learning:
            layers.append("v1.5-learning")
        if self.tools:
            layers.append("v1.6-tools")
        if self.improvement:
            layers.append("v1.7-improvement")
        if self.proposals:
            layers.append("v1.8-proposal")
        if self.approval:
            layers.append("v1.9-approval")
        if self.survival:
            layers.append("v3.0-survival")
        return layers
    
    def status(self) -> str:
        """Get status as human-readable string."""
        layers = self._get_active_layers()
        return f"{self.name} v{self.version} - {len(layers)} layers active"
    
    def get_state(self) -> Dict:
        """Get full entity state."""
        return {
            "name": self.name,
            "version": self.version,
            "layers": self._get_active_layers(),
            "survival": self.survival.get_full_status() if self.survival else None,
            "proposals": self.proposals.get_history() if self.proposals else {},
            "pending_approvals": len(self.approval.get_pending()) if self.approval else 0
        }


# Global singleton
_gluttony: Optional[GluttonyEntity] = None


def get_gluttony() -> GluttonyEntity:
    """Get the GLUTTONY entity instance."""
    global _gluttony
    if _gluttony is None:
        _gluttony = GluttonyEntity()
    return _gluttony
