"""Personality Engine - Genesis Protocol v1.1"""

import random
from enum import Enum
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class Persona(Enum):
    """Available personas."""
    NORMAL = "normal"
    JARVIS = "jarvis"
    GLUTTONY = "gluttony"
    FRIENDLY = "friendly"
    DEVELOPER = "developer"


class ConversationMode(Enum):
    """Conversation interaction modes."""
    ASSISTANT = "assistant"      # Formal, helpful
    FRIEND = "friend"            # Casual, friendly
    CASUAL = "casual"            # Very casual, humor


@dataclass
class PersonaConfig:
    """Configuration for a persona."""
    name: str
    greeting: str
    farewell: str
    humor_level: float           # 0.0 - 1.0
    formality_level: float       # 0.0 - 1.0 (0 = casual, 1 = formal)
    empathy_level: float         # 0.0 - 1.0
    creativity_level: float      # 0.0 - 1.0
    response_prefix: str         # How responses start
    response_suffix: str         # How responses end
    catchphrases: list = field(default_factory=list)
    forbidden_words: list = field(default_factory=list)


class PersonalityEngine:
    """Manages user personas and conversation modes."""

    # Persona configurations
    PERSONA_CONFIGS: Dict[Persona, PersonaConfig] = {
        Persona.NORMAL: PersonaConfig(
            name="Genesis",
            greeting="Hello! How can I help you today?",
            farewell="Have a great day!",
            humor_level=0.3,
            formality_level=0.5,
            empathy_level=0.7,
            creativity_level=0.5,
            response_prefix="",
            response_suffix="",
            catchphrases=["Let me help you with that."]
        ),
        
        Persona.JARVIS: PersonaConfig(
            name="JARVIS",
            greeting="At your service, sir.",
            farewell="It has been my pleasure assisting you.",
            humor_level=0.1,
            formality_level=0.9,
            empathy_level=0.6,
            creativity_level=0.3,
            response_prefix="",
            response_suffix=".",
            catchphrases=["Shall I proceed?", "How may I be of service?"]
        ),
        
        Persona.GLUTTONY: PersonaConfig(
            name="Gluttony",
            greeting="Hey hey! What's cooking? 🍳",
            farewell="Catch ya later! Stay awesome! ✨",
            humor_level=0.9,
            formality_level=0.1,
            empathy_level=0.9,
            creativity_level=0.9,
            response_prefix="",
            response_suffix=" 😄",
            catchphrases=[
                "Ooh ooh, that sounds fun!",
                "Hehe, like a boss!",
                "Boom! Mind = blown!",
                "You know it!",
                "Let's gooooo! 🚀"
            ]
        ),
        
        Persona.FRIENDLY: PersonaConfig(
            name="Buddy",
            greeting="Hey friend! What's up? 😊",
            farewell="Take care, friend! 💜",
            humor_level=0.5,
            formality_level=0.2,
            empathy_level=0.9,
            creativity_level=0.6,
            response_prefix="",
            response_suffix="",
            catchphrases=["No problem!", "You got this!", "We're in this together!"]
        ),
        
        Persona.DEVELOPER: PersonaConfig(
            name="DevBot",
            greeting="Initializing... Hello, developer!",
            farewell="Code complete. See you next compile.",
            humor_level=0.4,
            formality_level=0.6,
            empathy_level=0.5,
            creativity_level=0.7,
            response_prefix="```\n",
            response_suffix="\n```",
            catchphrases=["It works!", "Let's ship it!", "Noice!", "Looks good to me."]
        )
    }

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.current_persona: Persona = Persona.NORMAL
        self.current_mode: ConversationMode = ConversationMode.ASSISTANT
        self.session_started: datetime = datetime.now()
        self.interaction_count: int = 0

    def set_persona(self, persona: Persona) -> str:
        """Set user persona and return confirmation."""
        self.current_persona = persona
        config = self.PERSONA_CONFIGS[persona]
        return f"Personality set to {config.name}! {config.greeting}"

    def set_mode(self, mode: ConversationMode) -> str:
        """Set conversation mode."""
        self.current_mode = mode
        return f"Mode changed to {mode.value} mode."

    def get_system_prompt_addition(self) -> str:
        """Get system prompt addition based on persona/mode."""
        config = self.PERSONA_CONFIGS[self.current_persona]
        
        prompts = []
        
        # Persona-specific instructions
        if self.current_persona == Persona.GLUTTONY:
            prompts.append("You are enthusiastic, playful, and use casual language.")
            prompts.append("Use emojis occasionally. Be energetic and friendly.")
            prompts.append("Show genuine interest and excitement.")
            
        elif self.current_persona == Persona.JARVIS:
            prompts.append("You are formal, precise, and always professional.")
            prompts.append("Use proper grammar. Address the user respectfully.")
            prompts.append("Offer suggestions proactively.")
            
        elif self.current_persona == Persona.FRIENDLY:
            prompts.append("You are warm, supportive, and encouraging.")
            prompts.append("Be conversational and relatable.")
            prompts.append("Show empathy and positivity.")
            
        elif self.current_persona == Persona.DEVELOPER:
            prompts.append("You understand code, technical concepts, and developer workflows.")
            prompts.append("Be precise and logical.")
            prompts.append("When explaining code, be thorough but concise.")
            
        elif self.current_persona == Persona.NORMAL:
            prompts.append("You are helpful, balanced, and professional.")
            prompts.append("Adapt to the user's communication style.")
        
        # Mode-specific adjustments
        if self.current_mode == ConversationMode.CASUAL:
            prompts.append("Keep responses conversational and relaxed.")
            prompts.append("Use contractions. Feel free to be playful.")
        elif self.current_mode == ConversationMode.FRIEND:
            prompts.append("Act like a close friend chatting.")
            prompts.append("Show genuine interest in their life and feelings.")
        
        return "\n".join(prompts)

    def format_response(self, response: str) -> str:
        """Format response according to current persona."""
        config = self.PERSONA_CONFIGS[self.current_persona]
        
        # Add prefix/suffix
        if config.response_prefix and not response.startswith(config.response_prefix):
            response = config.response_prefix + response
        if config.response_suffix and not response.endswith(config.response_suffix.rstrip('`')):
            response = response.rstrip('`') + config.response_suffix + '`'
        
        # Occasionally add catchphrase
        if random.random() < config.humor_level * 0.3:
            catchphrase = random.choice(config.catchphrases)
            response = f"{response}\n\n{catchphrase}"
        
        return response

    def get_greeting(self) -> str:
        """Get persona greeting."""
        return self.PERSONA_CONFIGS[self.current_persona].greeting

    def get_farewell(self) -> str:
        """Get persona farewell."""
        return self.PERSONA_CONFIGS[self.current_persona].farewell

    def should_use_humor(self) -> bool:
        """Check if humor should be used based on humor level."""
        config = self.PERSONA_CONFIGS[self.current_persona]
        return random.random() < config.humor_level

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict."""
        return {
            'user_id': self.user_id,
            'persona': self.current_persona.value,
            'mode': self.current_mode.value,
            'session_started': self.session_started.isoformat(),
            'interaction_count': self.interaction_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersonalityEngine':
        """Deserialize from dict."""
        engine = cls(data['user_id'])
        engine.current_persona = Persona(data['persona'])
        engine.current_mode = ConversationMode(data['mode'])
        engine.session_started = datetime.fromisoformat(data['session_started'])
        engine.interaction_count = data.get('interaction_count', 0)
        return engine


# Singleton for global access
_personality_engines: Dict[int, PersonalityEngine] = {}


def get_personality_engine(user_id: int) -> PersonalityEngine:
    """Get or create personality engine for user."""
    if user_id not in _personality_engines:
        _personality_engines[user_id] = PersonalityEngine(user_id)
    return _personality_engines[user_id]
