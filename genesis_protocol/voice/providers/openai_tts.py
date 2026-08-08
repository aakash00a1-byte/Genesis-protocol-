"""OpenAI TTS Provider - Genesis Protocol v1.1"""

from typing import Optional
from ..tts import BaseTTSProvider
import os


class OpenAITTSProvider(BaseTTSProvider):
    """OpenAI Text-to-Speech provider."""
    
    VOICES = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
    MODELS = ['tts-1', 'tts-1-hd']
    
    def __init__(self):
        self.api_key = os.environ.get('OPENAI_API_KEY', '')
        self.voice = os.environ.get('OPENAI_TTS_VOICE', 'alloy')
        self.model = os.environ.get('OPENAI_TTS_MODEL', 'tts-1')
    
    def speak(self, text: str, voice: str = "default") -> bytes:
        """Convert text to speech using OpenAI TTS."""
        if not self.is_configured():
            raise RuntimeError("OpenAI TTS not configured")
        
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            
            voice_name = voice if voice in self.VOICES else self.voice
            
            response = client.audio.speech.create(
                model=self.model,
                voice=voice_name,
                input=text
            )
            return response.content
        except ImportError:
            raise RuntimeError("OpenAI not installed. Run: pip install openai")
    
    def is_configured(self) -> bool:
        """Check if OpenAI TTS is configured."""
        return bool(self.api_key)
