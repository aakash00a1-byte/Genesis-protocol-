"""Genesis Protocol - Image Processor

Image analysis, OCR, and vision processing.
"""

import io
from typing import Optional, Dict, Any
from PIL import Image
import pytesseract

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("processors.image")


class ImageProcessor:
    """
    Image processing for Genesis Protocol.
    
    Handles image analysis, OCR, and vision tasks.
    """
    
    def __init__(self):
        """Initialize image processor."""
        config = get_config()
        self.vision_provider = config.image.vision_provider
        self.vision_model = config.image.vision_model
        self.supported_formats = config.image.supported_formats
        self.max_width = config.image.max_width
        self.max_height = config.image.max_height
        self.max_size_mb = config.image.max_file_size_mb
        self.ocr_enabled = config.image.ocr_enabled
        self.ocr_language = config.image.ocr_language
        
        logger.info(f"Image processor initialized (Vision: {self.vision_provider})")
    
    async def analyze(self, image_stream: io.BytesIO) -> Optional[Dict[str, Any]]:
        """
        Analyze an image.
        
        Args:
            image_stream: Image file stream
            
        Returns:
            Analysis result dictionary
        """
        try:
            # Load image
            image_stream.seek(0)
            image = Image.open(image_stream)
            
            result = {
                "width": image.width,
                "height": image.height,
                "format": image.format,
                "mode": image.mode,
            }
            
            # OCR if enabled
            if self.ocr_enabled:
                text = self._extract_text(image)
                if text:
                    result["extracted_text"] = text
            
            # Basic description
            result["description"] = self._generate_description(image, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return None
    
    def _extract_text(self, image: Image.Image) -> Optional[str]:
        """
        Extract text from image using OCR.
        
        Args:
            image: PIL Image
            
        Returns:
            Extracted text or None
        """
        try:
            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Extract text
            text = pytesseract.image_to_string(
                image,
                lang=self.ocr_language,
            )
            
            return text.strip() if text else None
            
        except Exception as e:
            logger.warning(f"OCR extraction failed: {e}")
            return None
    
    def _generate_description(self, image: Image.Image, 
                               metadata: Dict) -> str:
        """
        Generate basic image description.
        
        Args:
            image: PIL Image
            metadata: Image metadata
            
        Returns:
            Description string
        """
        parts = []
        
        # Size info
        parts.append(f"Image size: {metadata['width']}x{metadata['height']}")
        
        # Format info
        parts.append(f"Format: {metadata.get('format', 'Unknown')}")
        
        # Aspect ratio
        if metadata['width'] > 0:
            ratio = metadata['height'] / metadata['width']
            if ratio > 1.5:
                parts.append("Portrait orientation")
            elif ratio < 0.67:
                parts.append("Landscape orientation")
            else:
                parts.append("Near-square orientation")
        
        return ". ".join(parts)
    
    async def ocr(self, image_stream: io.BytesIO) -> Optional[str]:
        """
        Perform OCR on image.
        
        Args:
            image_stream: Image file stream
            
        Returns:
            Extracted text
        """
        try:
            image_stream.seek(0)
            image = Image.open(image_stream)
            
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            text = pytesseract.image_to_string(image, lang=self.ocr_language)
            
            return text.strip() if text else None
            
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return None
    
    async def enhance_image(self, image_stream: io.BytesIO) -> Optional[bytes]:
        """
        Enhance image quality.
        
        Args:
            image_stream: Image file stream
            
        Returns:
            Enhanced image bytes
        """
        try:
            image_stream.seek(0)
            image = Image.open(image_stream)
            
            # Resize if too large
            if image.width > self.max_width or image.height > self.max_height:
                image.thumbnail((self.max_width, self.max_height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Save to bytes
            output = io.BytesIO()
            image.save(output, format="PNG", quality=95)
            output.seek(0)
            
            return output.read()
            
        except Exception as e:
            logger.error(f"Image enhancement failed: {e}")
            return None
    
    def validate_image(self, image_stream: io.BytesIO) -> bool:
        """
        Validate image file.
        
        Args:
            image_stream: Image file stream
            
        Returns:
            True if valid
        """
        try:
            image_stream.seek(0)
            image = Image.open(image_stream)
            
            # Check dimensions
            if image.width > self.max_width or image.height > self.max_height:
                logger.warning(f"Image too large: {image.width}x{image.height}")
                return False
            
            # Check format
            if image.format and image.format.upper() not in [f.upper() for f in self.supported_formats]:
                logger.warning(f"Unsupported format: {image.format}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return False