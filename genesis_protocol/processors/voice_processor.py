"""Genesis Protocol - Voice Processor

Speech-to-text and text-to-speech processing.
"""

import io
from typing import Optional
import tempfile
import os

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("processors.voice")


class VoiceProcessor:
    """
    Voice processing for Genesis Protocol.
    
    Handles speech-to-text (STT) and text-to-speech (TTS).
    """
    
    def __init__(self):
        """Initialize voice processor."""
        config = get_config()
        self.stt_provider = config.voice.stt_provider
        self.tts_provider = config.voice.tts_provider
        self.tts_voice_id = config.voice.tts_voice_id
        self.max_duration = config.voice.max_duration_seconds
        self.supported_formats = config.voice.supported_formats
        
        logger.info(f"Voice processor initialized (STT: {self.stt_provider}, TTS: {self.tts_provider})")
    
    async def transcribe(self, audio_stream: io.BytesIO, 
                         language: str = "auto") -> Optional[str]:
        """
        Transcribe audio to text.
        
        Args:
            audio_stream: Audio file stream
            language: Language code (auto for automatic detection)
            
        Returns:
            Transcribed text or None
        """
        try:
            if self.stt_provider == "whisper":
                return await self._transcribe_whisper(audio_stream, language)
            else:
                # Fallback to basic processing
                return await self._transcribe_basic(audio_stream)
                
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return None
    
    async def _transcribe_whisper(self, audio_stream: io.BytesIO, 
                                  language: str) -> Optional[str]:
        """
        Transcribe using Whisper API.
        
        Args:
            audio_stream: Audio file stream
            language: Language code
            
        Returns:
            Transcribed text
        """
        import httpx
        
        config = get_config()
        api_key = os.getenv("OPENAI_API_KEY", "")
        
        if not api_key:
            logger.warning("Whisper API key not configured")
            return None
        
        # Prepare audio for Whisper
        audio_stream.seek(0)
        audio_data = audio_stream.read()
        
        try:
            client = httpx.AsyncClient(timeout=60.0)
            
            files = {
                "file": ("audio.ogg", audio_data, "audio/ogg"),
            }
            
            data = {
                "model": config.voice.stt_model,
                "language": language if language != "auto" else None,
            }
            
            headers = {
                "Authorization": f"Bearer {api_key}",
            }
            
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                files=files,
                data=data,
                headers=headers,
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("text", "")
            else:
                logger.error(f"Whisper API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None
    
    async def _transcribe_basic(self, audio_stream: io.BytesIO) -> Optional[str]:
        """
        Basic transcription using SpeechRecognition library.
        
        Args:
            audio_stream: Audio file stream
            
        Returns:
            Transcribed text or None
        """
        try:
            import speech_recognition as sr
            import tempfile
            import wave
            
            logger.info("Using SpeechRecognition for transcription")
            
            # Save audio to temp file
            audio_stream.seek(0)
            audio_data = audio_stream.read()
            
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            # Transcribe
            recognizer = sr.Recognizer()
            with sr.AudioFile(temp_path) as source:
                audio = recognizer.record(source)
            
            # Try Google speech recognition (free tier)
            try:
                text = recognizer.recognize_google(audio)
                logger.info(f"Transcription successful: {len(text)} chars")
                return text
            except sr.UnknownValueError:
                logger.warning("Speech recognition could not understand audio")
                return None
            except sr.RequestError as e:
                logger.error(f"Speech recognition error: {e}")
                return None
            finally:
                # Cleanup temp file
                import os
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                
        except ImportError:
            logger.warning("SpeechRecognition library not available")
            return None
        except Exception as e:
            logger.error(f"Basic transcription failed: {e}")
            return None
    
    async def synthesize(self, text: str, voice_id: str = None) -> Optional[str]:
        """
        Synthesize text to speech.
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID (optional, uses default)
            
        Returns:
            Path to audio file or None
        """
        try:
            if self.tts_provider == "elevenlabs":
                return await self._synthesize_elevenlabs(text, voice_id)
            elif self.tts_provider == "gtts":
                return await self._synthesize_gtts(text)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return None
    
    async def _synthesize_elevenlabs(self, text: str, voice_id: str = None) -> Optional[str]:
        """
        Synthesize using ElevenLabs API.
        
        Args:
            text: Text to synthesize
            voice_id: Voice ID
            
        Returns:
            Path to audio file
        """
        import httpx
        import base64
        
        config = get_config()
        api_key = os.getenv("ELEVENLABS_API_KEY", "")
        
        if not api_key:
            logger.warning("ElevenLabs API key not configured")
            return None
        
        voice = voice_id or self.tts_voice_id
        
        try:
            client = httpx.AsyncClient(timeout=30.0)
            
            payload = {
                "text": text,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            }
            
            headers = {
                "Authorization": api_key,
                "Content-Type": "application/json",
            }
            
            response = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                json=payload,
                headers=headers,
            )
            
            if response.status_code == 200:
                # Save to temporary file
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(response.content)
                    return f.name
            else:
                logger.error(f"ElevenLabs API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"ElevenLabs synthesis failed: {e}")
            return None
    
    async def _synthesize_gtts(self, text: str) -> Optional[str]:
        """
        Synthesize using Google TTS (gtts).
        
        Args:
            text: Text to synthesize
            
        Returns:
            Path to audio file
        """
        try:
            from gtts import gTTS
            
            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            temp_path = temp_file.name
            temp_file.close()
            
            # Generate speech
            tts = gTTS(text=text, lang="en", slow=False)
            tts.save(temp_path)
            
            return temp_path
            
        except ImportError:
            logger.warning("gTTS not installed")
            return None
        except Exception as e:
            logger.error(f"gTTS synthesis failed: {e}")
            return None
    
    def validate_audio(self, audio_stream: io.BytesIO, duration_seconds: int) -> bool:
        """
        Validate audio file.
        
        Args:
            audio_stream: Audio file stream
            duration_seconds: Duration in seconds
            
        Returns:
            True if valid
        """
        if duration_seconds > self.max_duration:
            logger.warning(f"Audio too long: {duration_seconds}s > {self.max_duration}s")
            return False
        
        return True
    
    def cleanup_audio_file(self, file_path: str):
        """
        Clean up temporary audio file.
        
        Args:
            file_path: Path to file
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Failed to cleanup audio file: {e}")