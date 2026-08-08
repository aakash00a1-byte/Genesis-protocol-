"""Genesis Protocol - Channel Isolation System

Enforces strict separation between Web and Telegram channels:
- Web users only receive web responses
- Telegram users only receive Telegram responses
- Admin alerts only go to Telegram
- No cross-channel message leakage
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, Callable
from datetime import datetime

from genesis_protocol.utils.logger import get_logger

logger = get_logger("core.channel")


class Channel(Enum):
    """Communication channels."""
    WEB = "web"
    TELEGRAM = "telegram"
    UNKNOWN = "unknown"


class ChannelIsolation:
    """
    Channel isolation manager.
    
    Ensures messages from one channel never leak to another.
    """
    
    def __init__(self):
        """Initialize channel isolation."""
        self.logger = logging.getLogger("core.channel")
        self._active_channel: Optional[Channel] = None
        self._channel_history: List[Dict] = []
    
    def set_channel(self, channel: Channel):
        """Set the active channel for this request."""
        self._active_channel = channel
        self.logger.debug(f"Channel set to: {channel.value}")
    
    def get_channel(self) -> Channel:
        """Get the current active channel."""
        return self._active_channel or Channel.UNKNOWN
    
    def is_web(self) -> bool:
        """Check if current channel is web."""
        return self._active_channel == Channel.WEB
    
    def is_telegram(self) -> bool:
        """Check if current channel is telegram."""
        return self._active_channel == Channel.TELEGRAM
    
    def isolate(self, channel: Channel):
        """Context manager for channel isolation."""
        return ChannelContext(self, channel)
    
    def log_channel_activity(self, channel: Channel, action: str, details: str = ""):
        """Log channel-specific activity."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "channel": channel.value,
            "action": action,
            "details": details
        }
        self._channel_history.append(entry)
        
        # Keep last 1000 entries
        if len(self._channel_history) > 1000:
            self._channel_history = self._channel_history[-1000:]
    
    def get_history(self, limit: int = 100) -> List[Dict]:
        """Get channel activity history."""
        return self._channel_history[-limit:]


class ChannelContext:
    """Context manager for channel isolation."""
    
    def __init__(self, manager: 'ChannelIsolation', channel: Channel):
        self._manager = manager
        self._channel = channel
        self._previous: Optional[Channel] = None
    
    def __enter__(self):
        self._previous = self._manager._active_channel
        self._manager.set_channel(self._channel)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._manager.set_channel(self._previous)
        return False


@dataclass
class ChannelMessage:
    """Channel-specific message."""
    content: str
    channel: Channel
    user_id: str
    chat_id: Optional[int] = None
    metadata: Optional[Dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ChannelRouter:
    """
    Routes responses to the correct channel only.
    
    Web responses go to web.
    Telegram responses go to Telegram.
    Admin alerts go to Telegram only.
    """
    
    def __init__(self):
        """Initialize channel router."""
        self.logger = logging.getLogger("core.channel_router")
        self._web_sender: Optional[Callable] = None
        self._telegram_sender: Optional[Callable] = None
    
    def register_web_sender(self, sender: Callable):
        """Register web message sender."""
        self._web_sender = sender
    
    def register_telegram_sender(self, sender: Callable):
        """Register Telegram message sender."""
        self._telegram_sender = sender
    
    def send_to_channel(self, message: ChannelMessage) -> bool:
        """
        Send message ONLY to its designated channel.
        
        Never cross channels.
        """
        if message.channel == Channel.WEB and self._web_sender:
            try:
                self._web_sender(message)
                self.logger.info(f"Message sent to WEB channel for user {message.user_id}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to send to web: {e}")
                return False
        
        elif message.channel == Channel.TELEGRAM and self._telegram_sender:
            try:
                self._telegram_sender(message)
                self.logger.info(f"Message sent to TELEGRAM channel for chat {message.chat_id}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to send to telegram: {e}")
                return False
        
        else:
            self.logger.warning(f"No sender registered for channel {message.channel.value}")
            return False
    
    def send_web_only(self, user_id: str, content: str, **kwargs) -> bool:
        """Send message ONLY to web (never to Telegram)."""
        message = ChannelMessage(
            content=content,
            channel=Channel.WEB,
            user_id=user_id,
            **kwargs
        )
        return self.send_to_channel(message)
    
    def send_telegram_only(self, chat_id: int, content: str, **kwargs) -> bool:
        """Send message ONLY to Telegram (never to web)."""
        message = ChannelMessage(
            content=content,
            channel=Channel.TELEGRAM,
            user_id=str(chat_id),
            chat_id=chat_id,
            **kwargs
        )
        return self.send_to_channel(message)


# Singleton
_channel_isolation: Optional[ChannelIsolation] = None
_channel_router: Optional[ChannelRouter] = None


def get_channel_isolation() -> ChannelIsolation:
    """Get channel isolation singleton."""
    global _channel_isolation
    if _channel_isolation is None:
        _channel_isolation = ChannelIsolation()
    return _channel_isolation


def get_channel_router() -> ChannelRouter:
    """Get channel router singleton."""
    global _channel_router
    if _channel_router is None:
        _channel_router = ChannelRouter()
    return _channel_router


def detect_channel_from_request(request: Any) -> Channel:
    """
    Detect channel from incoming request.
    
    Args:
        request: HTTP request or Telegram update
        
    Returns:
        Detected channel
    """
    # Check for Flask/HTTP request
    if hasattr(request, 'headers'):
        user_agent = request.headers.get('User-Agent', '')
        
        # Web requests have specific patterns
        if 'Mozilla' in user_agent or 'Chrome' in user_agent or 'Safari' in user_agent:
            return Channel.WEB
        
        # API requests from web app
        if hasattr(request, 'path') and '/api/' in request.path:
            return Channel.WEB
        
        # Telegram bot webhook
        if hasattr(request, 'get_json'):
            try:
                data = request.get_json(silent=True)
                if data and ('message' in data or 'callback_query' in data):
                    return Channel.TELEGRAM
            except Exception:
                pass
    
    # Check for Telegram update
    if hasattr(request, 'effective_chat') or hasattr(request, 'message'):
        return Channel.TELEGRAM
    
    return Channel.UNKNOWN