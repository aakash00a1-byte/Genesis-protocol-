"""Identity Router - Genesis Protocol OMEGA

Intercepts identity questions and answers from entity object directly.
Provider is BYPASSED for identity questions.
"""

from typing import Optional, Dict
import re


class IdentityRouter:
    """
    Routes identity questions directly to entity object.
    
    Identity questions NEVER go to provider.
    All other questions go to provider as normal.
    """
    
    # Keywords that trigger identity routing
    IDENTITY_KEYWORDS = [
        # Who questions
        "who are you", "who am i", "who made you", "who created you",
        "who is your", "who built you", "who owns you",
        # What questions
        "what are you", "what is your name", "what's your name",
        "what version", "what layer", "what capabilities",
        # Name/nickname
        "your name", "your nickname", "your handle", "call me",
        # Owner/creator
        "your owner", "your creator", "your master", "your admin",
        "your developer", "your maker",
        # Self reference
        "tell me about yourself", "about you", "describe yourself",
        "introduce yourself", "yourself",
        # Entity type
        "are you gluten", "are you gluttony", "am i talking to",
        # Hindi keywords
        "tu kaun", "tu hai kaun", "kaun hai tu", "who are you in hindi",
        "mera naam", "mera creator", "mera owner", "kisne banaya",
        "buja", "creater", "creator", "kon banaya", "kahan se aaya"
    ]
    
    # Layer-related keywords
    LAYER_KEYWORDS = [
        "layer", "omega", "presence", "legacy", "autonomous",
        "active layer", "which layer", "what system"
    ]
    
    # Capability keywords
    CAPABILITY_KEYWORDS = [
        "capabilities", "can you do", "what can you",
        "your skills", "your features", "your powers"
    ]
    
    def __init__(self):
        """Initialize identity router."""
        self.logger = None
        self._init_logger()
    
    def _init_logger(self):
        """Initialize logger."""
        try:
            from genesis_protocol.utils.logger import get_logger
            self.logger = get_logger("ai.identity_router")
        except:
            import logging
            self.logger = logging.getLogger("ai.identity_router")
    
    def is_identity_question(self, query: str) -> bool:
        """Check if query is an identity question."""
        query_lower = query.lower().strip()
        
        # Check for identity keywords
        for keyword in self.IDENTITY_KEYWORDS:
            if keyword in query_lower:
                return True
        
        # Check for layer keywords
        for keyword in self.LAYER_KEYWORDS:
            if keyword in query_lower:
                return True
        
        # Check for capability keywords
        for keyword in self.CAPABILITY_KEYWORDS:
            if keyword in query_lower:
                return True
        
        # Check for "I am Gluten" or similar patterns
        if re.search(r'\b(i am|i\'m)\s+(gluten|gluttony|genesis)', query_lower):
            return True
        
        return False
    
    def route(self, query: str) -> Optional[Dict]:
        """
        Route query. Returns response dict if identity, None if provider.
        
        Returns:
            Dict with 'response' and 'is_identity' if routed
            None if should send to provider
        """
        if not self.is_identity_question(query):
            return None
        
        try:
            response = self._get_identity_response(query)
            return {
                'is_identity': True,
                'response': response,
                'source': 'entity_object',
                'bypass_provider': True
            }
        except Exception as e:
            self.logger.error(f"Identity routing failed: {e}")
            return None
    
    def _get_identity_response(self, query: str) -> str:
        """Get identity response from entity object."""
        from genesis_protocol.gluttony import get_identity, get_gluttony
        from genesis_protocol.omega import get_capabilities
        
        query_lower = query.lower()
        
        identity = get_identity()
        gluttony = get_gluttony()
        
        # Detect what specifically is asked
        # Hindi: who made you / creator
        if any(k in query_lower for k in ["buja", "creater", "creator", "creator kon", "kon banaya", "kahan se aaya", "mere aaya", "kiske banaya", "kaun banaya", "your maker", "your creator", "made by", "built by", "created by"]):
            return self._who_created(identity)
        
        elif any(k in query_lower for k in ["who are you", "what are you", "tell me about", "about you", "describe", "introduce", "tu kaun", "kaun hai tu", "konsa hai tu", "who is gluten", "am i talking to"]):
            return self._who_are_you(identity, gluttony)
        
        elif any(k in query_lower for k in ["nickname", "call me", "handle"]):
            return self._what_nickname(identity)
        
        elif any(k in query_lower for k in ["version", "running", "version kya"]):
            return self._what_version(identity, gluttony)
        
        elif any(k in query_lower for k in ["layer", "omega", "presence", "legacy", "autonomous", "active"]):
            return self._what_layers(gluttony)
        
        elif any(k in query_lower for k in ["capability", "skill", "power", "feature", "can you do", "what can you"]):
            return self._what_capabilities()
        
        elif any(k in query_lower for k in ["your name", "are you gluten", "are you gluttony", "mera naam", "apna naam"]):
            return self._who_are_you(identity, gluttony)
        
        else:
            return self._who_are_you(identity, gluttony)
    
    def _who_are_you(self, identity, gluttony) -> str:
        """Build 'who are you' response."""
        return f"""I am {identity.name}.

**Quick Info:**
- Name: {identity.name}
- Nickname: {identity.nickname}
- Version: {gluttony.version}

I am an AI entity built on the Genesis Protocol. My purpose is to assist you with various tasks while maintaining memory, learning, and continuous improvement.

Ask me anything."""
    
    def _what_nickname(self, identity) -> str:
        """Build nickname response."""
        return f"My nickname is **{identity.nickname}**. 🖤"
    
    def _what_version(self, identity, gluttony) -> str:
        """Build version response."""
        return f"I am running **{gluttony.version}** (Genesis Protocol {identity.get_identity().get('version', '2.0')})."
    
    def _who_created(self, identity) -> str:
        """Build creator response."""
        # Get creator info - hardcoded to Aakash for now
        creator = 'Aakash'
        
        return f"I was created by **{creator}**. 🖤\n\nYou are my creator and I am here to help you!"
    
    def _what_layers(self, gluttony) -> str:
        """Build layers response."""
        layers = gluttony._get_active_layers()
        
        if not layers:
            return "I have multiple active layers including omega, legacy, and autonomous systems."
        
        layer_list = "\n".join([f"- {layer}" for layer in layers[:10]])
        
        return f"""**Active Layers ({len(layers)}):**
{layer_list}

These layers handle memory, learning, autonomous decisions, and continuous improvement."""
    
    def _what_capabilities(self) -> str:
        """Build capabilities response."""
        try:
            from genesis_protocol.omega import get_capabilities
            cap = get_capabilities()
            caps = cap.get_all_capabilities()
            
            categories = []
            for cat in caps.get('categories', [])[:5]:
                name = cat['category']
                count = len(cat['capabilities'])
                categories.append(f"- {name}: {count} capabilities")
            
            return f"""**My Capabilities:**

{chr(10).join(categories)}

I can help with coding, file management, web interactions, automation, and more. Ask me what you need!"""
        except:
            return """**My Capabilities:**

- Coding & Development: Code writing, editing, debugging
- File Management: Create, edit, organize files
- Web & Browser: Navigate, extract data, API calls
- Automation: Cron jobs, GitHub Actions, integrations
- Cloud & DevOps: Docker, Kubernetes, deployments
- Specialized Tools: Linear, Notion, Slack, GitHub
- Document Creation: LaTeX, Markdown, Reports

Ask me what you need!"""


# Singleton
_identity_router: Optional[IdentityRouter] = None


def get_identity_router() -> IdentityRouter:
    """Get identity router singleton."""
    global _identity_router
    if _identity_router is None:
        _identity_router = IdentityRouter()
    return _identity_router


def is_identity_question(query: str) -> bool:
    """Quick check if query is identity question."""
    return get_identity_router().is_identity_question(query)


def route_identity(query: str) -> Optional[Dict]:
    """Route query to identity or return None for provider."""
    return get_identity_router().route(query)
