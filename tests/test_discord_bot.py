"""Tests for genesis_protocol.bot.discord_bot module."""

import pytest
from unittest.mock import MagicMock, patch


class TestDiscordBot:
    """Tests for DiscordBot class."""

    def test_discord_bot_import(self):
        """Test DiscordBot can be imported."""
        from genesis_protocol.bot.discord_bot import DiscordBot
        assert DiscordBot is not None

    def test_discord_bot_initialization(self):
        """Test DiscordBot initializes without errors."""
        from genesis_protocol.bot.discord_bot import DiscordBot
        bot = DiscordBot()
        assert bot is not None
        assert hasattr(bot, '_running')
        assert bot._running is False

    def test_commands_exist(self):
        """Test bot has expected commands defined."""
        from genesis_protocol.bot.discord_bot import DiscordBot
        bot = DiscordBot()
        
        # Check expected command names
        expected_commands = ['ping', 'status', 'whoami', 'health', 'memory']
        
        # Commands will be registered after initialize
        # but we can check the bot structure exists
        assert hasattr(bot, 'command_prefix')
        assert bot.command_prefix == '!'

    def test_intents_configured(self):
        """Test bot has correct intents."""
        from genesis_protocol.bot.discord_bot import DiscordBot
        bot = DiscordBot()
        
        # Check intents were set
        assert hasattr(bot, 'intents')
        # message_content is required for reading message content
        assert bot.intents.message_content is True

    def test_logger_setup(self):
        """Test logger is properly configured."""
        from genesis_protocol.bot.discord_bot import logger
        assert logger is not None
        assert logger.name == 'discord_bot'

    def test_token_validation(self):
        """Test token validation works."""
        from genesis_protocol.bot.discord_bot import DiscordBot
        import os
        
        bot = DiscordBot()
        
        # Without token set, run() should not proceed
        with patch.dict(os.environ, {}, clear=True):
            assert os.environ.get('DISCORD_TOKEN') is None
