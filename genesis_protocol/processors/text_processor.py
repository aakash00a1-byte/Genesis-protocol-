"""Genesis Protocol - Text Processor

Text preprocessing and sanitization.
"""

from typing import Optional

from genesis_protocol.utils.sanitizers import Sanitizer
from genesis_protocol.utils.logger import get_logger

logger = get_logger("processors.text")


class TextProcessor:
    """
    Text preprocessing for Genesis Protocol.
    
    Handles text cleaning, truncation, and formatting.
    """
    
    def __init__(self):
        """Initialize text processor."""
        self.sanitizer = Sanitizer()
    
    def clean(self, text: str) -> str:
        """
        Clean text input.
        
        Args:
            text: Input text
            
        Returns:
            Cleaned text
        """
        if not text:
            return ""
        
        # Basic cleaning
        text = text.strip()
        text = " ".join(text.split())  # Normalize whitespace
        
        return text
    
    def sanitize(self, text: str) -> str:
        """
        Sanitize text for safe processing.
        
        Args:
            text: Input text
            
        Returns:
            Sanitized text
        """
        return self.sanitizer.sanitize_text(text)
    
    def truncate(self, text: str, max_length: int = 10000) -> str:
        """
        Truncate text to maximum length.
        
        Args:
            text: Input text
            max_length: Maximum characters
            
        Returns:
            Truncated text
        """
        if not text:
            return ""
        
        if len(text) <= max_length:
            return text
        
        return text[:max_length] + "\n\n[Content truncated...]"
    
    def extract_keywords(self, text: str, max_keywords: int = 10) -> list:
        """
        Extract keywords from text.
        
        Args:
            text: Input text
            max_keywords: Maximum keywords to extract
            
        Returns:
            List of keywords
        """
        if not text:
            return []
        
        # Simple keyword extraction
        words = text.lower().split()
        
        # Filter common words
        stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "is", "are", "was", "were"
        }
        
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        
        # Get unique keywords
        unique = list(dict.fromkeys(keywords))[:max_keywords]
        
        return unique
    
    def detect_language(self, text: str) -> str:
        """
        Detect language of text.
        
        Args:
            text: Input text
            
        Returns:
            Language code (en, es, fr, de, etc.)
        """
        # Simple language detection
        # In production, use a proper library like langdetect
        
        if not text:
            return "en"
        
        # Check for common patterns
        if any(word in text.lower() for word in ["hola", "gracias", "buenos"]):
            return "es"
        if any(word in text.lower() for word in ["bonjour", "merci", "s'il"]):
            return "fr"
        if any(word in text.lower() for word in ["danke", "bitte", "guten"]):
            return "de"
        
        return "en"