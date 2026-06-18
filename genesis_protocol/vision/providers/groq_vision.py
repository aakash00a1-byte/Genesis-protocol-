"""Groq Vision Provider - Genesis Protocol v1.1"""

from typing import Optional
from ..vision_providers import BaseVisionProvider
import os
import base64


class GroqVisionProvider(BaseVisionProvider):
    """Groq Vision API provider using llama-3.2-11b-vision."""
    
    def __init__(self):
        self.api_key = os.environ.get('GROQ_API_KEY', '')
        self.model = os.environ.get('GROQ_VISION_MODEL', 'llama-3.2-11b-vision-preview')
    
    def analyze(self, image_data: bytes, prompt: str = "Describe this image") -> str:
        """Analyze image using Groq Vision API."""
        if not self.is_configured():
            raise RuntimeError("Groq Vision not configured")
        
        try:
            import httpx
            
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            if image_data[:3] == b'\xff\xd8\xff':
                mime_type = 'image/jpeg'
            elif image_data[:8] == b'\x89PNG\r\n\x1a\n':
                mime_type = 'image/png'
            else:
                mime_type = 'image/jpeg'
            
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}
                            }
                        ]
                    }
                ],
                "temperature": 0.5,
                "max_tokens": 1024
            }
            
            response = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30.0
            )
            
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
            
        except ImportError:
            raise RuntimeError("httpx not installed")
    
    def is_configured(self) -> bool:
        return bool(self.api_key)
