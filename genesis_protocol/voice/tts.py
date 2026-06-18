"""Text-to-Speech providers - Genesis Protocol v1.1"""

from abc import ABC, abstractmethod
from typing import Optional, Dict
import os


class BaseTTSProvider(ABC):
    """Abstract base class for TTS providers."""
    
    @abstractmethod
    def speak(self, text: str, voice: str = "default") -> bytes:
        """Convert text to speech and return audio bytes."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass


class TextToSpeechProvider:
    """Text-to-speech provider with fallback support."""
    
    def __init__(self):
        self.providers: Dict[str, BaseTTSProvider] = {}
        self._register_providers()
    
    def _register_providers(self):
        """Register available TTS providers."""
        # gTTS (free, no API key needed)
        try:
            from .providers.gtts_provider import GTTSProvider
            self.providers['gtts'] = GTTSProvider()
        except ImportError:
            pass
        
        # OpenAI TTS (if available)
        try:
            from .providers.openai_tts import OpenAITTSProvider
            self.providers['openai'] = OpenAITTSProvider()
        except ImportError:
            pass
        
        # Google Cloud TTS (if available)
        try:
            from .providers.google_tts import GoogleTTSProvider
            self.providers['google'] = GoogleTTSProvider()
        except ImportError:
            pass
    
    def speak(
        self, 
        text: str, 
        voice: str = "default",
        provider: Optional[str] = None
    ) -> bytes:
        """Convert text to speech with fallback."""
        if provider and provider in self.providers:
            p = self.providers[provider]
            if p.is_configured():
                return p.speak(text, voice)
        
        # Try providers in order
        for name, p in self.providers.items():
            if p.is_configured():
                try:
                    return p.speak(text, voice)
                except Exception:
                    continue
        
        raise RuntimeError("No TTS provider configured")
    
    def get_available_providers(self) -> list:
        """Get list of configured providers."""
        return [
            name for name, p in self.providers.items() 
            if p.is_configured()
        ]
