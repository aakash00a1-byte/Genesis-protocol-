"""Vision Pipeline - Genesis Protocol v1.4
Image upload, analysis, and memory storage."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime
import logging

logger = logging.getLogger("interaction.vision")


@dataclass
class ImageAnalysis:
    """Analysis of an image."""
    image_id: str
    description: str
    objects: List[str]
    text_detected: str = ""
    tags: List[str] = None
    provider: str = "unknown"
    timestamp: datetime = None


class VisionPipeline:
    """Vision interaction pipeline."""
    
    def __init__(self):
        self.provider = None
        self._image_history: List[Dict] = []
    
    def configure_provider(self, provider_name: str = "groq"):
        """Configure vision provider."""
        try:
            if provider_name == "groq":
                from genesis_protocol.vision.providers import GroqVisionProvider
                self.provider = GroqVisionProvider()
                logger.info("Vision configured: Groq Vision")
            elif provider_name == "openai":
                from genesis_protocol.vision.providers import OpenAIVisionProvider
                self.provider = OpenAIVisionProvider()
                logger.info("Vision configured: OpenAI Vision")
        except Exception as e:
            logger.warning(f"Vision configuration failed: {e}")
    
    def validate_image(self, image_data: bytes) -> bool:
        """Validate image data."""
        # Check for JPEG/PNG headers
        if image_data[:3] == b'\xff\xd8\xff':  # JPEG
            return True
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':  # PNG
            return True
        return False
    
    def analyze_image(
        self,
        image_data: bytes,
        prompt: str = "Describe this image in detail.",
        user_id: int = 0
    ) -> Optional[ImageAnalysis]:
        """Analyze an image."""
        if not self.provider:
            logger.warning("No vision provider configured")
            return None
        
        if not self.validate_image(image_data):
            logger.error("Invalid image data")
            return None
        
        try:
            # Call vision provider
            description = self.provider.analyze(image_data, prompt)
            
            # Create analysis object
            analysis = ImageAnalysis(
                image_id=f"img_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                description=description,
                objects=[],  # Would extract from description
                provider=self.provider.__class__.__name__,
                timestamp=datetime.now()
            )
            
            # Store in history
            self._image_history.append({
                'id': analysis.image_id,
                'description': description,
                'timestamp': analysis.timestamp.isoformat()
            })
            
            # Store summary in memory
            self._store_image_memory(analysis, user_id)
            
            logger.info(f"Image analyzed: {analysis.image_id}")
            return analysis
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return None
    
    def analyze_multiple(
        self,
        images: List[bytes],
        prompt: str = "Describe these images and their relationships.",
        user_id: int = 0
    ) -> List[ImageAnalysis]:
        """Analyze multiple images."""
        results = []
        
        for img_data in images:
            analysis = self.analyze_image(img_data, prompt, user_id)
            if analysis:
                results.append(analysis)
        
        return results
    
    def _store_image_memory(self, analysis: ImageAnalysis, user_id: int):
        """Store image analysis in memory."""
        try:
            from genesis_protocol.memory import get_long_term_memory, MemoryImportance
            
            ltm = get_long_term_memory()
            
            # Store description
            ltm.add_memory(
                content=f"[Image] {analysis.description}",
                user_id=user_id,
                importance=MemoryImportance.MEDIUM,
                category="image_analysis"
            )
            
            logger.debug(f"Image memory stored: {analysis.image_id}")
            
        except Exception as e:
            logger.error(f"Failed to store image memory: {e}")
    
    def get_image_history(self, limit: int = 10) -> List[Dict]:
        """Get recent image analyses."""
        return self._image_history[-limit:]
    
    def get_status(self) -> Dict[str, Any]:
        """Get vision pipeline status."""
        return {
            'provider_configured': self.provider is not None,
            'provider': self.provider.__class__.__name__ if self.provider else None,
            'images_analyzed': len(self._image_history)
        }


# Global singleton
_vision_pipeline: Optional[VisionPipeline] = None


def get_vision_pipeline() -> VisionPipeline:
    """Get global vision pipeline."""
    global _vision_pipeline
    if _vision_pipeline is None:
        _vision_pipeline = VisionPipeline()
    return _vision_pipeline
