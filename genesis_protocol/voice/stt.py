"""Speech-to-Text providers - Genesis Protocol v1.1"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import base64
import os


class BaseSTTProvider(ABC):
    """Abstract base class for STT providers."""
    
    @abstractmethod
    def transcribe(self, audio_data: bytes, language: str = "en") -> str:
        """Transcribe audio to text."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass


class SpeechToTextProvider:
    """Speech-to-text provider with fallback support."""
    
    def __init__(self):
        self.providers: Dict[str, BaseSTTProvider] = {}
        self._register_providers()
    
    def _register_providers(self):
        """Register available STT providers."""
        # Groq Whisper (if available)
        try:
            from .providers.groq_whisper import GroqWhisperSTT
            self.providers['groq'] = GroqWhisperSTT()
        except ImportError:
            pass
        
        # OpenAI Whisper (if available)
        try:
            from .providers.openai_whisper import OpenAIWhisperSTT
            self.providers['openai'] = OpenAIWhisperSTT()
        except ImportError:
            pass
    
    def transcribe(
        self, 
        audio_data: bytes, 
        language: str = "en",
        provider: Optional[str] = None
    ) -> str:
        """Transcribe audio to text with fallback."""
        if provider and provider in self.providers:
            p = self.providers[provider]
            if p.is_configured():
                return p.transcribe(audio_data, language)
        
        # Try providers in order
        for name, p in self.providers.items():
            if p.is_configured():
                try:
                    return p.transcribe(audio_data, language)
                except Exception:
                    continue
        
        raise RuntimeError("No STT provider configured")
    
    def get_available_providers(self) -> list:
        """Get list of configured providers."""
        return [
            name for name, p in self.providers.items() 
            if p.is_configured()
        ]
