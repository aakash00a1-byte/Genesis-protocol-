"""Voice Pipeline - Genesis Protocol v1.4
STT → AI → TTS integration."""

from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger("interaction.voice")


@dataclass
class VoiceMessage:
    """A voice message."""
    audio_data: bytes
    text: str
    language: str = "en"
    duration_seconds: float = 0
    timestamp: datetime = None


@dataclass
class VoiceResponse:
    """A voice response."""
    text: str
    audio_data: Optional[bytes] = None
    tts_provider: Optional[str] = None


class VoicePipeline:
    """Voice conversation pipeline."""
    
    def __init__(self):
        self.stt_provider = None
        self.tts_provider = None
        self._continuous_mode = False
        self._interrupt_flag = False
    
    def configure_stt(self, provider_name: str = "groq"):
        """Configure speech-to-text provider."""
        try:
            if provider_name == "groq":
                # Would integrate with Whisper
                logger.info("STT configured: Groq Whisper")
            elif provider_name == "openai":
                logger.info("STT configured: OpenAI Whisper")
        except Exception as e:
            logger.error(f"STT configuration failed: {e}")
    
    def configure_tts(self, provider_name: str = "gtts"):
        """Configure text-to-speech provider."""
        try:
            from genesis_protocol.voice import get_tts_provider
            self.tts_provider = get_tts_provider(provider_name)
            logger.info(f"TTS configured: {provider_name}")
        except Exception as e:
            logger.warning(f"TTS configuration failed: {e}")
    
    def set_continuous_mode(self, enabled: bool):
        """Enable/disable continuous conversation mode."""
        self._continuous_mode = enabled
        logger.info(f"Continuous voice mode: {enabled}")
    
    def interrupt(self):
        """Interrupt current voice processing."""
        self._interrupt_flag = True
        logger.info("Voice processing interrupted")
    
    def speech_to_text(self, audio_data: bytes, language: str = "en") -> str:
        """Convert speech to text."""
        if self._interrupt_flag:
            self._interrupt_flag = False
            return ""
        
        try:
            if not self.stt_provider:
                logger.warning("No STT provider configured")
                return ""
            
            # Would call STT provider
            text = self.stt_provider.transcribe(audio_data, language=language)
            logger.debug(f"STT result: {text[:50]}...")
            return text
            
        except Exception as e:
            logger.error(f"STT failed: {e}")
            return ""
    
    def text_to_speech(self, text: str, language: str = "en") -> bytes:
        """Convert text to speech."""
        try:
            if not self.tts_provider:
                logger.warning("No TTS provider configured")
                return b""
            
            audio_data = self.tts_provider.speak(text, language=language)
            logger.debug(f"TTS generated {len(audio_data)} bytes")
            return audio_data
            
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return b""
    
    def process_voice_message(
        self,
        audio_data: bytes,
        ai_callback,  # Function to call AI
        language: str = "en"
    ) -> VoiceResponse:
        """Process a complete voice message: STT → AI → TTS."""
        # Step 1: Speech to Text
        text = self.speech_to_text(audio_data, language)
        
        if not text or self._interrupt_flag:
            return VoiceResponse(text="", audio_data=b"")
        
        # Step 2: Get AI response (call the provided callback)
        try:
            ai_response = ai_callback(text)
        except Exception as e:
            logger.error(f"AI processing failed: {e}")
            ai_response = "I'm sorry, I couldn't process that."
        
        # Step 3: Text to Speech
        audio_data = self.text_to_speech(ai_response, language)
        
        return VoiceResponse(
            text=ai_response,
            audio_data=audio_data,
            tts_provider=self.tts_provider.__class__.__name__ if self.tts_provider else None
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get voice pipeline status."""
        return {
            'stt_configured': self.stt_provider is not None,
            'tts_configured': self.tts_provider is not None,
            'continuous_mode': self._continuous_mode,
            'tts_provider': self.tts_provider.__class__.__name__ if self.tts_provider else None
        }


# Global singleton
_voice_pipeline: Optional[VoicePipeline] = None


def get_voice_pipeline() -> VoicePipeline:
    """Get global voice pipeline."""
    global _voice_pipeline
    if _voice_pipeline is None:
        _voice_pipeline = VoicePipeline()
    return _voice_pipeline
