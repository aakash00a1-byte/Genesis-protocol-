"""Genesis Protocol - Response Formatters

Telegram-specific response formatting.
"""

import re
from typing import Optional

from genesis_protocol.utils.logger import get_logger

logger = get_logger("formatters")


class Formatter:
    """
    Response formatter for Telegram messages.
    
    Handles markdown, HTML, and special formatting.
    """
    
    # Telegram escape characters
    ESCAPE_CHARS = re.compile(r'([_*\[\]`~>#\+\-=|{}\.!\\])')
    
    # Markdown patterns
    CODE_BLOCK_PATTERN = re.compile(r'```(\w+)?\n(.*?)```', re.DOTALL)
    INLINE_CODE_PATTERN = re.compile(r'`([^`]+)`')
    BOLD_PATTERN = re.compile(r'\*\*([^*]+)\*\*')
    ITALIC_PATTERN = re.compile(r'\*([^*]+)\*')
    LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    @classmethod
    def escape_markdown(cls, text: str) -> str:
        """
        Escape special characters for Telegram markdown.
        
        Args:
            text: Input text
            
        Returns:
            Escaped text
        """
        if not text:
            return ""
        
        return cls.ESCAPE_CHARS.sub(r'\\\1', text)
    
    @classmethod
    def escape_html(cls, text: str) -> str:
        """
        Escape special characters for Telegram HTML.
        
        Args:
            text: Input text
            
        Returns:
            Escaped text
        """
        if not text:
            return ""
        
        replacements = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
        }
        
        for char, escaped in replacements.items():
            text = text.replace(char, escaped)
        
        return text
    
    @classmethod
    def format_markdown(cls, text: str) -> str:
        """
        Format text with Telegram markdown.
        
        Args:
            text: Input text
            
        Returns:
            Formatted text
        """
        if not text:
            return ""
        
        # Escape existing markdown
        text = cls.escape_markdown(text)
        
        return text
    
    @classmethod
    def format_code_block(cls, code: str, language: str = None) -> str:
        """
        Format code block for Telegram.
        
        Args:
            code: Code content
            language: Programming language
            
        Returns:
            Formatted code block
        """
        if not code:
            return ""
        
        # Escape content
        escaped = cls.escape_markdown(code)
        
        if language:
            return f"```{language}\n{escaped}\n```"
        return f"```\n{escaped}\n```"
    
    @classmethod
    def format_response(cls, text: str, style: str = "markdown") -> str:
        """
        Format AI response for Telegram.
        
        Args:
            text: Response text
            style: Formatting style (markdown, html, plain)
            
        Returns:
            Formatted response
        """
        if not text:
            return ""
        
        # Apply style-specific formatting
        if style == "html":
            return cls.format_html(text)
        elif style == "plain":
            return cls.format_plain(text)
        else:
            return cls.format_markdown(text)
    
    @classmethod
    def format_html(cls, text: str) -> str:
        """
        Format text with HTML tags.
        
        Args:
            text: Input text
            
        Returns:
            HTML formatted text
        """
        if not text:
            return ""
        
        # Convert markdown-style formatting to HTML
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        
        return text
    
    @classmethod
    def format_plain(cls, text: str) -> str:
        """
        Format text as plain (no formatting).
        
        Args:
            text: Input text
            
        Returns:
            Plain text
        """
        if not text:
            return ""
        
        # Remove markdown formatting
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^*]+)\*', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        return text
    
    @classmethod
    def truncate_response(cls, text: str, max_length: int = 4096) -> str:
        """
        Truncate response to Telegram message limit.
        
        Args:
            text: Response text
            max_length: Maximum length
            
        Returns:
            Truncated response
        """
        if not text:
            return ""
        
        if len(text) <= max_length:
            return text
        
        return text[:max_length - 20] + "\n\n[Response truncated...]"
    
    @classmethod
    def format_list(cls, items: list, numbered: bool = False) -> str:
        """
        Format list for Telegram message.
        
        Args:
            items: List items
            numbered: Use numbered list
            
        Returns:
            Formatted list
        """
        if not items:
            return ""
        
        lines = []
        for i, item in enumerate(items, 1):
            prefix = f"{i}. " if numbered else "• "
            lines.append(f"{prefix}{item}")
        
        return "\n".join(lines)
    
    @classmethod
    def format_error(cls, error: str, include_trace: bool = False) -> str:
        """
        Format error message for user.
        
        Args:
            error: Error message
            include_trace: Include stack trace
            
        Returns:
            Formatted error
        """
        message = f"❌ Error: {error}"
        
        if include_trace:
            message += "\n\nPlease contact support with this error."
        
        return message
    
    @classmethod
    def format_success(cls, message: str) -> str:
        """
        Format success message.
        
        Args:
            message: Success message
            
        Returns:
            Formatted message
        """
        return f"✅ {message}"
    
    @classmethod
    def format_warning(cls, message: str) -> str:
        """
        Format warning message.
        
        Args:
            message: Warning message
            
        Returns:
            Formatted message
        """
        return f"⚠️ {message}"
    
    @classmethod
    def format_info(cls, message: str) -> str:
        """
        Format info message.
        
        Args:
            message: Info message
            
        Returns:
            Formatted message
        """
        return f"ℹ️ {message}"