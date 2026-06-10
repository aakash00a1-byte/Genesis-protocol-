"""
Genesis Protocol - Autonomous Multimodal AI Agent

An autonomous AI agent system with Telegram interface that processes text,
voice, and image inputs through an intelligent multi-provider AI fallback chain.
"""

__version__ = "1.0.0-dev"
__author__ = "Genesis Protocol Team"

from genesis_protocol.config import Config
from genesis_protocol.models import Message, User, Conversation

__all__ = ["Config", "Message", "User", "Conversation", "__version__"]