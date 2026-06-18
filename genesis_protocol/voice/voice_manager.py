"""Voice Manager - Genesis Protocol v1.1"""

from typing import Optional
from .stt import SpeechToTextProvider
from .tts import TextToSpeechProvider


class VoiceManager:
    """Manages voice input/output for the assistant."""
    
    def __init__(self):
        self.stt = SpeechToTextProvider()
        self.tts = TextToSpeechProvider()
    
    def process_voice_input(self, audio_data: bytes, language: str = "en") -> str:
        """Process voice input and return text."""
        return self.stt.transcribe(audio_data, language)
    
    def process_voice_output(self, text: str, voice: str = "default") -> bytes:
        """Process text and return voice audio."""
        return self.tts.speak(text, voice)
    
    def get_status(self) -> dict:
        """Get voice system status."""
        return {
            'stt_providers': self.stt.get_available_providers(),
            'tts_providers': self.tts.get_available_providers(),
            'voice_enabled': bool(
                self.stt.get_available_providers() or 
                self.tts.get_available_providers()
            )
        }
