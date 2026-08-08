"""Image Analyzer - Genesis Protocol v1.1"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import base64
import io
from PIL import Image


@dataclass
class ImageAnalysis:
    """Result of image analysis."""
    description: str
    objects_detected: List[str]
    text_found: Optional[str]
    faces_detected: int
    confidence: float
    provider_used: str


class ImageAnalyzer:
    """Analyzes uploaded images using vision AI."""
    
    def __init__(self):
        self.provider = None
        self._init_provider()
    
    def _init_provider(self):
        """Initialize vision provider."""
        try:
            from genesis_protocol.vision.vision_providers import VisionProvider
            self.provider = VisionProvider()
        except ImportError:
            pass
    
    def analyze(
        self, 
        image_data: bytes,
        prompt: str = "Describe this image in detail"
    ) -> ImageAnalysis:
        """Analyze an image."""
        if not self.provider:
            raise RuntimeError("Vision provider not available")
        
        # Verify image is valid
        try:
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size
        except Exception:
            raise ValueError("Invalid image data")
        
        # Call provider
        description = self.provider.analyze(image_data, prompt)
        
        return ImageAnalysis(
            description=description,
            objects_detected=[],  # Will be enhanced with detection
            text_found=None,
            faces_detected=0,
            confidence=0.95,
            provider_used=self.provider.get_available_providers()[0] if self.provider.get_available_providers() else 'unknown'
        )
    
    def get_status(self) -> Dict[str, Any]:
        """Get image analyzer status."""
        return {
            'available': self.provider is not None,
            'providers': self.provider.get_available_providers() if self.provider else []
        }
