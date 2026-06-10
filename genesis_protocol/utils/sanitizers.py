"""Genesis Protocol - Input Sanitizers

Security-focused input sanitization and validation.
"""

import html
import re
from typing import Optional

from genesis_protocol.utils.logger import get_logger

logger = get_logger("sanitizers")


class Sanitizer:
    """
    Input sanitization for Genesis Protocol.
    
    Provides security-focused sanitization for user inputs.
    """
    
    # Patterns for dangerous content
    HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
    SCRIPT_PATTERN = re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
    SQL_INJECTION_PATTERN = re.compile(
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER)\b)|"
        r"(--)|(\bOR\b\s+\d+\s*=\s*\d+)|(\bAND\b\s+\d+\s*=\s*\d+)",
        re.IGNORECASE
    )
    XSS_PATTERN = re.compile(
        r"javascript:|on\w+\s*=|data:text/html|<iframe|<object|<embed",
        re.IGNORECASE
    )
    
    @classmethod
    def sanitize_text(cls, text: str, max_length: int = 10000) -> str:
        """
        Sanitize text input.
        
        Args:
            text: Input text
            max_length: Maximum allowed length
            
        Returns:
            Sanitized text
        """
        if not text:
            return ""
        
        # Truncate to max length
        text = text[:max_length]
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # HTML escape
        text = html.escape(text)
        
        # Remove any remaining HTML tags
        text = cls.HTML_TAG_PATTERN.sub('', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    @classmethod
    def sanitize_markdown(cls, text: str, max_length: int = 10000) -> str:
        """
        Sanitize markdown input (allows some markdown).
        
        Args:
            text: Input text
            max_length: Maximum allowed length
            
        Returns:
            Sanitized markdown
        """
        if not text:
            return ""
        
        # Truncate
        text = text[:max_length]
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # Allow common markdown but escape dangerous content
        # Keep: **bold**, *italic*, `code`, ```code blocks```, [links](url)
        # Remove: HTML tags, scripts, event handlers
        
        text = cls.SCRIPT_PATTERN.sub('', text)
        text = cls.XSS_PATTERN.sub('[blocked]', text)
        
        # Normalize whitespace
        text = ' '.join(text.split())
        
        return text.strip()
    
    @classmethod
    def check_sql_injection(cls, text: str) -> bool:
        """
        Check for SQL injection patterns.
        
        Args:
            text: Input text
            
        Returns:
            bool: True if suspicious pattern found
        """
        return bool(cls.SQL_INJECTION_PATTERN.search(text))
    
    @classmethod
    def check_xss(cls, text: str) -> bool:
        """
        Check for XSS patterns.
        
        Args:
            text: Input text
            
        Returns:
            bool: True if suspicious pattern found
        """
        return bool(cls.XSS_PATTERN.search(text))
    
    @classmethod
    def validate_file_type(cls, filename: str, allowed: list) -> bool:
        """
        Validate file type by extension.
        
        Args:
            filename: File name
            allowed: List of allowed extensions
            
        Returns:
            bool: True if allowed
        """
        if not filename:
            return False
        
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        return ext in [e.lower() for e in allowed]
    
    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitize filename to prevent path traversal.
        
        Args:
            filename: File name
            
        Returns:
            Sanitized filename
        """
        if not filename:
            return "unnamed"
        
        # Remove path components
        filename = filename.rsplit('/', 1)[-1]
        filename = filename.rsplit('\\', 1)[-1]
        
        # Remove dangerous characters
        filename = re.sub(r'[^\w\s\-\.]', '_', filename)
        
        # Limit length
        filename = filename[:255]
        
        return filename or "unnamed"
    
    @classmethod
    def validate_chat_id(cls, chat_id: int) -> bool:
        """
        Validate Telegram chat ID.
        
        Args:
            chat_id: Chat ID
            
        Returns:
            bool: True if valid
        """
        return isinstance(chat_id, int) and chat_id != 0
    
    @classmethod
    def validate_user_id(cls, user_id: int) -> bool:
        """
        Validate Telegram user ID.
        
        Args:
            user_id: User ID
            
        Returns:
            bool: True if valid
        """
        return isinstance(user_id, int) and user_id > 0
    
    @classmethod
    def truncate_for_ai(cls, text: str, max_chars: int = 8000) -> str:
        """
        Truncate text for AI processing.
        
        Args:
            text: Input text
            max_chars: Maximum characters
            
        Returns:
            Truncated text
        """
        if not text:
            return ""
        
        if len(text) <= max_chars:
            return text
        
        return text[:max_chars] + "\n\n[Content truncated due to length...]"