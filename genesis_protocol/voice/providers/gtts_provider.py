"""gTTS Provider - Genesis Protocol v1.1"""

from typing import Optional
from ..tts import BaseTTSProvider
import os


class GTTSProvider(BaseTTSProvider):
    """Google Text-to-Speech provider (free, no API key)."""
    
    def __init__(self):
        self._configured = True  # gTTS doesn't need API key
    
    def speak(self, text: str, voice: str = "default") -> bytes:
        """Convert text to speech using gTTS."""
        try:
            from gtts import gTTS
            import io
            
            lang = self._voice_to_lang(voice)
            tts = gTTS(text=text, lang=lang, slow=False)
            
            mp3_buffer = io.BytesIO()
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)
            return mp3_buffer.read()
        except ImportError:
            raise RuntimeError("gTTS not installed. Run: pip install gTTS")
    
    def is_configured(self) -> bool:
        """Check if gTTS is available."""
        try:
            from gtts import gTTS
            return self._configured
        except ImportError:
            return False
    
    def _voice_to_lang(self, voice: str) -> str:
        """Map voice name to language code."""
        voice_map = {
            'default': 'en',
            'en': 'en',
            'english': 'en',
            'hi': 'hi',
            'hindi': 'hi',
            'es': 'es',
            'spanish': 'es',
            'fr': 'fr',
            'french': 'fr',
            'de': 'de',
            'german': 'de',
            'zh': 'zh-CN',
            'chinese': 'zh-CN',
            'ja': 'ja',
            'japanese': 'ja',
        }
        return voice_map.get(voice.lower(), 'en')
