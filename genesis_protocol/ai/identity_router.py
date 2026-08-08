"""Identity Router - Genesis Protocol OS

Intercepts identity questions and answers from entity object directly.
Provider is BYPASSED for identity questions.

Confidence System:
- EXPLICIT: User directly stated
- OBSERVED: Available metadata/persisted records
- INFERRED: Derived from patterns/behavior
- UNKNOWN: No evidence exists
"""

from typing import Optional, Dict, List
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
        "layer", "gluttony_os", "presence", "legacy", "autonomous",
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
        except Exception:
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
        from genesis_protocol.gluttony_os import get_capabilities
        
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
        
        elif any(k in query_lower for k in ["layer", "gluttony_os", "presence", "legacy", "autonomous", "active"]):
            return self._what_layers(gluttony)
        
        elif any(k in query_lower for k in ["capability", "skill", "power", "feature", "can you do", "what can you"]):
            return self._what_capabilities()
        
        elif any(k in query_lower for k in ["test", "testing", "test cases", "test files", "kya kya test"]):
            return self._what_tests(identity)
        
        # User name questions - check confidence system
        elif any(k in query_lower for k in ["my name", "mera naam", "who am i", "what's my name", "my identity", "mera naam"]):
            if "you" not in query_lower and "tu" not in query_lower:
                # Asking about USER, not entity
                return self._what_is_user_name()
        
        elif any(k in query_lower for k in ["your name", "are you gluten", "are you gluttony", "apna naam"]):
            return self._who_are_you(identity, gluttony)
        
        else:
            return self._who_are_you(identity, gluttony)
    
    def _who_are_you(self, identity, gluttony) -> str:
        """Build 'who are you' response with EXPLICIT confidence."""
        # Entity identity is ALWAYS explicit (hardcoded)
        return f"""I am **{identity.name}** (nickname: **{identity.nickname}**).

**Identity [EXPLICIT - I know this for certain]:**
- Name: {identity.name}
- Nickname: {identity.nickname}
- Variant: {identity.variant}
- Creator: {identity.creator}
- Protocol: Genesis Protocol {identity.protocol_version}

**System Info:**
- Layers: {len(identity.layers)} active
- Capabilities: {len(identity.capabilities)} features
- Tests: {identity.tests['total']} test files

I am an AI entity on the Genesis Protocol OS. 🖤"""
    
    def _what_nickname(self, identity) -> str:
        """Build nickname response with EXPLICIT confidence."""
        return f"My nickname is **{identity.nickname}** [EXPLICIT - hardcoded]. 🖤\n\nYou can call me {identity.nickname}!"
    
    def _what_version(self, identity, gluttony) -> str:
        """Build version response with EXPLICIT confidence."""
        return f"""**Version Info [EXPLICIT - I know this for certain]:**
- Protocol: Genesis Protocol **{identity.protocol_version}**
- Variant: **{identity.variant}**
- Identity Version: {identity.get_identity().get('version', '2.0')}

I am running on the OS variant! 🖤"""
    
    def _who_created(self, identity) -> str:
        """Build creator response with EXPLICIT confidence."""
        return f"""**Creator Info [EXPLICIT - I know this for certain]:**
- Creator: **{identity.creator}**
- Entity: {identity.name}
- Variant: {identity.variant}

You created me and I am here to serve you! 🖤"""
    
    def _what_is_user_name(self, user_id: int = None) -> str:
        """
        Get user's name with proper confidence.
        User's name may be EXPLICIT (stated), OBSERVED (metadata), 
        INFERRED (pattern), or UNKNOWN.
        """
        from genesis_protocol.ai.trust_confidence import get_trust_system
        
        trust = get_trust_system()
        result = trust.get_user_identity(user_id)
        
        if result["status"] == "unknown":
            return result["message"]
        
        if result["message"]:
            return result["message"]
        
        return f"Your name is {result['data']}."""
    
    def _what_tests(self, identity) -> str:
        """Build tests response."""
        tests = identity.tests
        test_list = "\n".join([f"- {t}" for t in tests['unit'][:5]])
        
        return f"""**Implemented Tests ({tests['total']}):**
{test_list}
...

Status: {tests['status']}"""
    
    def _what_capabilities(self) -> str:
        """Build capabilities response."""
        caps = self._get_all_capabilities_list()
        cap_list = "\n".join([f"- {c}" for c in caps[:10]])
        
        return f"""**My Capabilities:**
{cap_list}
...

Total: {len(caps)} capabilities. Ask me what you need! 🖤"""
    
    def _get_all_capabilities_list(self) -> List[str]:
        """Get all capabilities."""
        try:
            from genesis_protocol.gluttony_os import get_capabilities
            cap = get_capabilities()
            all_caps = cap.get_all_capabilities()
            
            caps = []
            for cat in all_caps.get('categories', []):
                for cap_item in cat.get('capabilities', []):
                    caps.append(cap_item.get('name', 'unknown'))
            return caps
        except Exception:
            return [
                "chat", "memory", "learning", "autonomous",
                "web_navigation", "api_calls", "file_management",
                "code_execution", "automation", "self_improvement"
            ]
    
    def _what_layers(self, identity) -> str:
        """Build layers response."""
        # Use identity.layers for consistent info
        layers = identity.layers
        
        layer_list = "\n".join([f"- {layer}" for layer in layers])
        
        return f"""**Active Layers ({len(layers)}):**
{layer_list}

These layers handle memory, learning, autonomous decisions, and continuous improvement. 🖤"""
    
    def _what_capabilities(self) -> str:
        """Build capabilities response."""
        try:
            from genesis_protocol.gluttony_os import get_capabilities
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
        except Exception:
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
