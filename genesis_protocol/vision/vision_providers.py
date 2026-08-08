"""Vision Providers - Genesis Protocol v1.1"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, List
import base64
import os


class BaseVisionProvider(ABC):
    """Abstract base class for vision providers."""
    
    @abstractmethod
    def analyze(self, image_data: bytes, prompt: str = "Describe this image") -> str:
        """Analyze image and return description."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is configured."""
        pass


class VisionProvider:
    """Vision provider with fallback support."""
    
    def __init__(self):
        self.providers: Dict[str, BaseVisionProvider] = {}
        self._register_providers()
    
    def _register_providers(self):
        """Register available vision providers."""
        # Groq Vision (if available)
        try:
            from .providers.groq_vision import GroqVisionProvider
            self.providers['groq'] = GroqVisionProvider()
        except ImportError:
            pass
        
        # OpenAI Vision (if available)
        try:
            from .providers.openai_vision import OpenAIVisionProvider
            self.providers['openai'] = OpenAIVisionProvider()
        except ImportError:
            pass
        
        # Claude Vision (if available)
        try:
            from .providers.claude_vision import ClaudeVisionProvider
            self.providers['claude'] = ClaudeVisionProvider()
        except ImportError:
            pass
    
    def analyze(
        self, 
        image_data: bytes, 
        prompt: str = "Describe this image",
        provider: Optional[str] = None
    ) -> str:
        """Analyze image with fallback."""
        if provider and provider in self.providers:
            p = self.providers[provider]
            if p.is_configured():
                return p.analyze(image_data, prompt)
        
        # Try providers in order
        for name, p in self.providers.items():
            if p.is_configured():
                try:
                    return p.analyze(image_data, prompt)
                except Exception:
                    continue
        
        raise RuntimeError("No vision provider configured")
    
    def get_available_providers(self) -> List[str]:
        """Get list of configured providers."""
        return [
            name for name, p in self.providers.items() 
            if p.is_configured()
        ]
