"""GLUTTONY Core - Genesis Protocol OS

The unified entity - truth over appearance, evidence over claims."""

from typing import Dict, List, Optional
from datetime import datetime


class GluttonyEntity:
    """The GLUTTONY AI Entity."""
    
    def __init__(self, name: str = "GLUTTONY"):
        self.name = name
        self.version = "OS"
        self.created_at = datetime.now()
        self.last_active = datetime.now()
        self._init_layers()
    
    def _init_layers(self):
        """Initialize all Genesis Protocol layers."""
        # v1.3-v3.0 layers
        try:
            from genesis_protocol.autonomous import get_autonomous_daemon
            self.autonomous = get_autonomous_daemon()
        except:
            self.autonomous = None
        
        try:
            from genesis_protocol.interaction import get_context_manager
            self.context = get_context_manager()
        except:
            self.context = None
        
        try:
            from genesis_protocol.learning import get_evaluation_engine
            self.learning = get_evaluation_engine()
        except:
            self.learning = None
        
        try:
            from genesis_protocol.tools import get_tool_registry
            self.tools = get_tool_registry()
        except:
            self.tools = None
        
        try:
            from genesis_protocol.improvement import get_weakness_detector
            self.improvement = get_weakness_detector()
        except:
            self.improvement = None
        
        try:
            from genesis_protocol.proposal import get_proposal_manager
            self.proposals = get_proposal_manager()
        except:
            self.proposals = None
        
        try:
            from genesis_protocol.approval import get_approval_manager
            self.approval = get_approval_manager()
        except:
            self.approval = None
        
        try:
            from genesis_protocol.survival import get_survival_manager
            self.survival = get_survival_manager()
        except:
            self.survival = None
        
        # OS layer
        try:
            from genesis_protocol.gluttony_os import get_self_knowledge, get_journal, get_trust_builder, get_autonomy_controller
            self.self_knowledge = get_self_knowledge()
            self.journal = get_journal()
            self.trust_builder = get_trust_builder()
            self.autonomy = get_autonomy_controller()
        except:
            self.self_knowledge = None
            self.journal = None
            self.trust_builder = None
            self.autonomy = None
    
    def think(self, message: str, context: Dict = None) -> Dict:
        """Process a message."""
        self.last_active = datetime.now()
        
        # Journal the interaction
        if self.journal:
            self.journal.observe(f"User: {message}")
        
        response = {
            "entity": self.name,
            "version": self.version,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "layers": self._get_layers(),
            "response": self._generate_response(message)
        }
        
        return response
    
    def _generate_response(self, message: str) -> str:
        """Generate appropriate response based on message."""
        msg_lower = message.lower()
        
        if "who are you" in msg_lower:
            return self.self_knowledge.end_state_response() if self.self_knowledge else self._default_response()
        
        if "status" in msg_lower:
            return self.status()
        
        return f"I am {self.name}. How can I help?"
    
    def _default_response(self) -> str:
        return f"I am {self.name}, version {self.version}."
    
    def _get_layers(self) -> List[str]:
        """Get active layers."""
        layers = []
        if self.autonomous: layers.append("v1.3-autonomous")
        if self.context: layers.append("v1.4-interaction")
        if self.learning: layers.append("v1.5-learning")
        if self.tools: layers.append("v1.6-tools")
        if self.improvement: layers.append("v1.7-improvement")
        if self.proposals: layers.append("v1.8-proposal")
        if self.approval: layers.append("v1.9-approval")
        if self.survival: layers.append("v3.0-survival")
        if self.self_knowledge: layers.append("OS-self-knowledge")
        if self.journal: layers.append("OS-journal")
        if self.trust_builder: layers.append("OS-trust")
        if self.autonomy: layers.append("OS-autonomy")
        return layers
    
    def observe(self) -> Dict:
        """Self-observe."""
        obs = {
            "name": self.name,
            "version": self.version,
            "uptime": str(datetime.now() - self.created_at),
            "layers": self._get_layers()
        }
        
        if self.self_knowledge:
            obs["metrics"] = self.self_knowledge.get_metrics()
        
        if self.autonomy:
            obs["autonomy_level"] = self.autonomy.get_level()
        
        return obs
    
    def status(self) -> str:
        """Get status."""
        layers = self._get_layers()
        return f"{self.name} v{self.version} - {len(layers)} layers"
    
    def _get_active_layers(self) -> Dict:
        """Get active layers with count (for API compatibility)."""
        layers = self._get_layers()
        return {
            "count": len(layers),
            "layers": [layer.split("-")[-1] for layer in layers]
        }
    
    def describe_self(self) -> str:
        """Full self-description."""
        if self.self_knowledge:
            return self.self_knowledge.describe_self()
        return f"{self.name} v{self.version}"
    
    def get_state(self) -> Dict:
        """Get full state."""
        return {
            "entity": self.name,
            "version": self.version,
            "layers": self._get_layers(),
            "metrics": self.self_knowledge.get_metrics() if self.self_knowledge else {},
            "autonomy": self.autonomy.get_status() if self.autonomy else {},
            "survival": self.survival.get_full_status() if self.survival else {}
        }


_gluttony: Optional[GluttonyEntity] = None


def get_gluttony() -> GluttonyEntity:
    global _gluttony
    if _gluttony is None:
        _gluttony = GluttonyEntity()
    return _gluttony
