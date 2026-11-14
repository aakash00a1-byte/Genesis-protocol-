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
        "buja", "creater", "creator", "kon banaya", "kisne banaya",
        "kisne bnaya", "kon bnaya", "kahan se aaya",
        # Hinglish variants ("tum" and "aap" forms, and the misspellings a
        # speaker actually types). Without these the question fell through to
        # the provider, which then invented an identity ("I am Google BARD").
        "tum kaun", "tum kon", "tum kaun ho", "tum kon ho", "aap kaun",
        "aap kon", "aap kaun ho", "kya ho tum", "tum kya ho", "tumhe kisne banaya",
        "tumhara naam", "tumhara name", "tumhara nam", "aapka naam",
        "apna naam", "tera naam", "tumhari identity",
    ]

    # Provider/model keywords. Answered from the live configuration, never
    # guessed: the provider that replies to a request is reported per request.
    PROVIDER_MODEL_KEYWORDS = [
        "which model", "what model", "your model", "tum kis model",
        "kaunsa model", "konsa model", "kis model", "model kya",
        "your provider", "which provider", "what provider", "kis provider",
        "kaunsa provider", "konsa provider", "provider kya", "kis ai",
        "kaunse ai", "konsi ai", "kis llm", "which llm", "what llm",
        "kaunse brain", "which brain", "kis engine", "which engine",
    ]
    
    # Layer-related keywords
    LAYER_KEYWORDS = [
        "layer", "gluten_os", "presence", "legacy", "autonomous",
        "active layer", "which layer", "what system"
    ]
    
    # Capability keywords
    CAPABILITY_KEYWORDS = [
        "capabilities", "can you do", "what can you",
        "your skills", "your features", "your powers"
    ]

    # GitHub / repository *status* keywords. Answered from the live read-only
    # github_status module, never guessed. Deliberately status-intent phrases:
    # a bare "github" or "repository" is general knowledge and must still reach
    # the provider, not this status dump.
    GITHUB_KEYWORDS = [
        "github connected", "github status", "github se juda", "github juda",
        "repo connected", "repo status", "repository connected",
        "is github connected", "is the repo connected",
        "open prs", "open pull request", "open pull requests",
        "khuli pr", "kitni pr", "pr ka status", "my pull requests",
        "pull requests kya", "how many prs",
    ]

    # Work-order / task *status* keywords. Answered from the live work-order
    # store. Status-intent only, for the same reason as above.
    WORK_KEYWORDS = [
        "work order", "work orders", "my work orders", "mere work order",
        "my tasks", "mere tasks", "task status", "mere kaam ka status",
        "kaam ka status", "pending tasks", "pending work", "work queue",
        "kya kaam chal raha", "kaam chal raha",
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

        # Check for provider/model keywords
        for keyword in self.PROVIDER_MODEL_KEYWORDS:
            if keyword in query_lower:
                return True

        # Check for capability keywords
        for keyword in self.CAPABILITY_KEYWORDS:
            if keyword in query_lower:
                return True

        # Check for GitHub / work-order status keywords
        for keyword in self.GITHUB_KEYWORDS:
            if keyword in query_lower:
                return True
        for keyword in self.WORK_KEYWORDS:
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
        from genesis_protocol.gluten import get_identity, get_gluten
        from genesis_protocol.gluten_os import get_capabilities
        
        query_lower = query.lower()
        
        identity = get_identity()
        gluten = get_gluten()
        
        # Detect what specifically is asked
        # Hindi: who made you / creator
        if any(k in query_lower for k in ["buja", "creater", "creator", "creator kon", "kon banaya", "kisne banaya", "kisne bnaya", "kahan se aaya", "mere aaya", "kiske banaya", "kaun banaya", "kisne", "your maker", "your creator", "who made you", "who created you", "who built you", "made by", "built by", "created by"]):
            return self._who_created(identity)
        
        elif any(k in query_lower for k in ["who are you", "what are you", "tell me about", "about you", "describe", "introduce", "tu kaun", "kaun hai tu", "konsa hai tu", "who is gluten", "am i talking to"]):
            return self._who_are_you(identity, gluten)
        
        elif any(k in query_lower for k in ["nickname", "call me", "handle"]):
            return self._what_nickname(identity)
        
        elif any(k in query_lower for k in ["version", "running", "version kya"]):
            return self._what_version(identity, gluten)
        
        elif any(k in query_lower for k in ["layer", "gluten_os", "presence", "legacy", "autonomous", "active"]):
            return self._what_layers(gluten)
        
        elif any(k in query_lower for k in ["capability", "skill", "power", "feature", "can you do", "what can you"]):
            return self._what_capabilities()

        elif any(k in query_lower for k in self.GITHUB_KEYWORDS):
            return self._what_github()

        elif any(k in query_lower for k in self.WORK_KEYWORDS):
            return self._what_work_orders()

        elif any(k in query_lower for k in self.PROVIDER_MODEL_KEYWORDS):
            return self._what_provider_model()
        
        elif any(k in query_lower for k in ["test", "testing", "test cases", "test files", "kya kya test"]):
            return self._what_tests(identity)
        
        # User name questions - check confidence system
        elif any(k in query_lower for k in ["my name", "mera naam", "who am i", "what's my name", "my identity", "mera naam"]):
            if "you" not in query_lower and "tu" not in query_lower:
                # Asking about USER, not entity
                return self._what_is_user_name()
        
        elif any(k in query_lower for k in ["your name", "are you gluten", "are you gluttony", "apna naam"]):
            return self._who_are_you(identity, gluten)
        
        else:
            return self._who_are_you(identity, gluten)
    
    def _who_are_you(self, identity, gluten) -> str:
        """Build 'who are you' response with EXPLICIT confidence."""
        # Entity identity is ALWAYS explicit (hardcoded)
        return (
            f"Main {identity.name} hoon, nickname {identity.nickname}. "
            f"{identity.name} se pehle main {identity.lineage().replace(' -> ', ', phir ')} "
            f"tha. {identity.creator} ne mujhe banaya, aur main Genesis Protocol "
            f"{identity.protocol_version} par ek AI entity hoon - koi fixed model "
            f"nahi. Abhi {len(identity.layers)} layers active hain."
        )
    
    def _what_provider_model(self) -> str:
        """Report the real providers/models, read from the live configuration.

        This is the answer that used to be invented by the provider itself
        ("I run on Google Vertex AI"). It never guesses and never prints a
        credential - only the configured provider/model names and availability.
        """
        try:
            from genesis_protocol.agentic.identity import describe_runtime
            runtime = describe_runtime()
        except Exception:
            return (
                "I can't read my runtime configuration right now, so I won't "
                "guess which model is behind me. Try the `/api/identity` endpoint."
            )

        available = runtime.get("providers_available") or []
        default_provider = runtime.get("default_provider")
        default_model = runtime.get("default_model")

        if not available:
            return (
                "No AI provider is configured in this process, so no model is "
                "answering - I am running on my own fallback text. Set a provider "
                "key (e.g. GROQ_API_KEY) to give me a real model."
            )

        lines = [
            "**Runtime [EXPLICIT - read from live configuration, not guessed]:**",
            f"- Entity: {runtime.get('entity', 'GLUTEN')}",
            f"- Providers available: {', '.join(available)}",
            f"- Chain default: {default_provider} / {default_model}",
            "",
            "The scoring engine may pick a different *configured* provider for a "
            "given query; the provider and model that actually answered are "
            "reported with each response. I am not a single fixed model.",
        ]
        return "\n".join(lines)

    def _what_nickname(self, identity) -> str:
        """Build nickname response with EXPLICIT confidence."""
        return f"Mera nickname {identity.nickname} hai. Aap mujhe {identity.nickname} bula sakte hain."
    
    def _what_version(self, identity, gluten) -> str:
        """Build version response with EXPLICIT confidence."""
        return (
            f"Main Genesis Protocol {identity.protocol_version} par chalta hoon, "
            f"{identity.variant} variant. Meri lineage {identity.lineage()} hai, aur "
            f"identity version {identity.get_identity().get('version', '2.0')} hai."
        )
    
    def _who_created(self, identity) -> str:
        """Build creator response with EXPLICIT confidence."""
        return (
            f"Mujhe {identity.creator} ne banaya hai. Main {identity.name} hoon, "
            f"Genesis Protocol {identity.variant} variant par."
        )
    
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
    
    def _get_all_capabilities_list(self) -> List[str]:
        """Get all capabilities."""
        try:
            from genesis_protocol.gluten_os import get_capabilities
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
        return (
            f"{len(layers)} layers active hain: "
            + ", ".join(layers)
            + ". Ye memory, learning, autonomous decisions aur continuous "
            "improvement sambhalte hain."
        )
    
    def _what_capabilities(self) -> str:
        """Capabilities response built from what can actually run here.

        The previous version printed a fixed marketing list - docker, cloud,
        kubernetes - whether or not the backing binary existed, which is how
        the agent came to claim capabilities it could not exercise.
        """
        available, unavailable = self._runtime_tool_summary()
        runnable_skills = self._runtime_skill_summary()

        report = ["**My Capabilities (checked against this deployment):**", ""]
        if available:
            report.append("Tools that work right now: " + ", ".join(available))
        if runnable_skills:
            report.append("Skills with at least one working tool: " + ", ".join(runnable_skills))
        if unavailable:
            report.append(
                "Declared but NOT usable here (missing binary or integration): "
                + ", ".join(unavailable)
            )
        report.append("")
        report.append(
            "Limits: code runs in a bounded sandbox (CPU/memory capped, secrets "
            "stripped); restricted tools need the owner; background autonomy is "
            "off, so execution is caller-driven."
        )
        return "\n".join(report)

    def _runtime_tool_summary(self):
        """Split registered tools into those that can run and those that cannot."""
        from genesis_protocol.tools.tool_registry import get_tool_registry

        registry = get_tool_registry()
        available, unavailable = [], []
        for meta in registry.get_all_tools():
            (available if meta.is_available() else unavailable).append(meta.name)
        return sorted(available), sorted(unavailable)

    def _runtime_skill_summary(self) -> List[str]:
        """Skills that have at least one tool which can actually run."""
        from genesis_protocol.skills import get_skill_registry
        from genesis_protocol.tools.skill_tools import tools_for_skill

        return [
            skill.name
            for skill in get_skill_registry().list_all_skills()
            if tools_for_skill(skill.name)
        ]

    def _what_github(self) -> str:
        """Report the live, read-only GitHub connection status.

        Reads the same ``integrations.github_status`` the Telegram ``/github``
        command and the web ``/api/github`` endpoint use, so the chat answer and
        the other surfaces cannot disagree. Read-only: never merges or pushes.
        """
        try:
            from genesis_protocol.integrations.github_status import format_status, status

            return format_status(status())
        except Exception as exc:  # noqa: BLE001 - report, never invent a status
            return f"GitHub status check nahi ho paya: {str(exc)[:150]}"

    def _what_work_orders(self) -> str:
        """List the owner's work orders, read from the durable queue.

        The queue file is the one the Telegram webhook parks ``/do`` orders in
        (``web/app.py``). Read-only: this never runs, cancels or merges one.
        """
        import json
        import os

        path = os.environ.get("GLUTEN_WORK_ORDER_QUEUE", "/tmp/telegram_task_queue.json")
        try:
            if not os.path.exists(path):
                return "Koi work order nahi hai. Naya order Telegram se: /do <instruction>"
            with open(path, encoding="utf-8") as handle:
                orders = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            return f"Work orders padh nahi paya: {str(exc)[:150]}"

        if not isinstance(orders, list) or not orders:
            return "Koi work order nahi hai. Naya order Telegram se: /do <instruction>"

        icon = {"queued": "🕓", "running": "⚙️", "done": "✅", "failed": "❌", "cancelled": "🚫"}
        lines = [f"{len(orders)} work order(s):"]
        for order in orders[-10:]:
            if not isinstance(order, dict):
                continue
            mark = icon.get(order.get("state", ""), "•")
            extra = order.get("pr") or order.get("note") or ""
            lines.append(
                f"{mark} #{order.get('id')} [{order.get('state')}] "
                f"{str(order.get('instruction', ''))[:60]}"
                + (f" — {extra}" if extra else "")
            )
        lines.append("Ye read-only list hai; order dene ke liye: /do <instruction>")
        return "\n".join(lines)



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
