"""
Genesis Protocol - Autonomous Multimodal AI Agent v1.2

An autonomous AI agent system with Telegram interface that processes text,
voice, and image inputs through an intelligent multi-provider AI fallback chain.
"""

__version__ = "1.2.0"
__author__ = "Genesis Protocol Team"

from genesis_protocol.config import Config
from genesis_protocol.models import Message, User, Conversation
from genesis_protocol.integration import GenesisIntegration, get_integration

__all__ = [
    "Config", "Message", "User", "Conversation", 
    "__version__",
    "GenesisIntegration", "get_integration"
]