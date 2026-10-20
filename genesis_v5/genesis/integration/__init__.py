"""Chat-platform integration (Discord/Telegram) into the governed Kernel.

Nothing here executes a chat message directly: text is scanned, parsed into a
command, and routed through the same authority gate and bounded autonomy loop
as any other request.
"""
from genesis.integration.discord import DiscordClient
from genesis.integration.gateway import (
    ChatCommand,
    ChatGateway,
    ChatReply,
    parse_command,
    to_tool_requests,
)
from genesis.integration.runner import (
    DiscordRunner,
    TelegramRunner,
    build_runners,
)
from genesis.integration.telegram import TelegramClient

__all__ = [
    "ChatCommand",
    "ChatGateway",
    "ChatReply",
    "DiscordClient",
    "DiscordRunner",
    "TelegramClient",
    "TelegramRunner",
    "build_runners",
    "parse_command",
    "to_tool_requests",
]
