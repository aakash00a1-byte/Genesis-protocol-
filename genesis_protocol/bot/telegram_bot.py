"""Genesis Protocol - Telegram Bot

Core Telegram bot implementation with handlers.
"""

import asyncio
from typing import Optional, Dict, Any

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, filters
)

from genesis_protocol.config import get_config, Config
from genesis_protocol.utils.logger import get_logger, setup_logging
from genesis_protocol.bot.handlers.message_handler import MessageHandler as GenesisMessageHandler
from genesis_protocol.bot.handlers.command_handler import CommandHandler as GenesisCommandHandler
from genesis_protocol.bot.handlers.voice_handler import VoiceHandler
from genesis_protocol.bot.handlers.image_handler import ImageHandler

logger = get_logger("bot")


class TelegramBot:
    """
    Genesis Protocol Telegram Bot.
    
    Handles all Telegram interactions including messages, 
    voice notes, images, and commands.
    """
    
    def __init__(self, config: Config = None):
        """
        Initialize Telegram bot.
        
        Args:
            config: Optional configuration (uses global if not provided)
        """
        self.config = config or get_config()
        self._app: Optional[Application] = None
        self._running = False
        
        # Handlers
        self.message_handler = GenesisMessageHandler(self)
        self.command_handler = GenesisCommandHandler(self)
        self.voice_handler = VoiceHandler(self)
        self.image_handler = ImageHandler(self)
        
        logger.info("Telegram bot initialized")
    
    async def initialize(self):
        """Initialize the bot application."""
        if not self.config.telegram.bot_token:
            raise ValueError("Telegram bot token not configured")
        
        self._app = Application.builder().token(self.config.telegram.bot_token).build()
        
        # Register handlers
        self._register_handlers()
        
        logger.info("Telegram bot application initialized")
    
    def _register_handlers(self):
        """Register all bot handlers."""
        # Command handlers
        self._app.add_handler(CommandHandler("start", self.command_handler.handle_start))
        self._app.add_handler(CommandHandler("help", self.command_handler.handle_help))
        self._app.add_handler(CommandHandler("settings", self.command_handler.handle_settings))
        self._app.add_handler(CommandHandler("stats", self.command_handler.handle_stats))
        self._app.add_handler(CommandHandler("reset", self.command_handler.handle_reset))
        self._app.add_handler(CommandHandler("model", self.command_handler.handle_model))
        self._app.add_handler(CommandHandler("debug", self.command_handler.handle_debug))
        self._app.add_handler(CommandHandler("deploy", self.command_handler.handle_deploy))
        self._app.add_handler(CommandHandler("models", self.command_handler.handle_models))
        
        # Message handlers
        self._app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.message_handler.handle_text
        ))
        
        # Voice handler
        self._app.add_handler(MessageHandler(
            filters.VOICE, 
            self.voice_handler.handle_voice
        ))
        
        # Image handler
        self._app.add_handler(MessageHandler(
            filters.PHOTO, 
            self.image_handler.handle_image
        ))
        
        # Callback handler
        self._app.add_handler(CallbackQueryHandler(
            self.message_handler.handle_callback
        ))
        
        # Error handler
        self._app.add_error_handler(self.handle_error)
    
    async def start(self, webhook_url: str = None):
        """
        Start the bot.
        
        Args:
            webhook_url: Optional webhook URL for webhook mode
        """
        if not self._app:
            await self.initialize()
        
        self._running = True
        
        if webhook_url:
            # Webhook mode
            await self._app.run_webhook(
                listen="0.0.0.0",
                port=self.config.app_port,
                url_path="webhook",
                webhook_url=webhook_url,
            )
        else:
            # Polling mode
            await self._app.initialize()
            await self._app.start()
            await self._app.updater.start_polling()
            
            logger.info("Bot started in polling mode")
            
            # Keep running
            while self._running:
                await asyncio.sleep(1)
    
    async def stop(self):
        """Stop the bot."""
        self._running = False
        
        if self._app:
            if self._app.updater:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        
        logger.info("Bot stopped")
    
    async def handle_error(self, update: Update, context):
        """
        Handle bot errors.
        
        Args:
            update: Telegram update
            context: Error context
        """
        error = context.error
        logger.error(
            f"Bot error: {error}",
            error_type=type(error).__name__,
            update=update.to_dict() if update else None
        )
        
        # Try to notify user
        if update and update.effective_chat:
            try:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⚠️ An error occurred. Please try again."
                )
            except Exception:
                pass
    
    async def send_message(self, chat_id: int, text: str, 
                           parse_mode: str = "Markdown",
                           reply_to: int = None) -> bool:
        """
        Send a message to a chat.
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Parse mode (Markdown, HTML, None)
            reply_to: Optional message ID to reply to
            
        Returns:
            True if successful
        """
        if not self._app:
            return False
        
        try:
            kwargs = {
                "chat_id": chat_id,
                "text": text,
            }
            
            if parse_mode:
                kwargs["parse_mode"] = parse_mode
            
            if reply_to:
                kwargs["reply_to_message_id"] = reply_to
            
            await self._app.bot.send_message(**kwargs)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    async def send_typing(self, chat_id: int):
        """Send typing indicator."""
        if not self._app:
            return
        
        try:
            await self._app.bot.send_chat_action(
                chat_id=chat_id,
                action="typing"
            )
        except Exception:
            pass
    
    async def send_voice(self, chat_id: int, file_path: str) -> bool:
        """
        Send voice message.
        
        Args:
            chat_id: Telegram chat ID
            file_path: Path to audio file
            
        Returns:
            True if successful
        """
        if not self._app:
            return False
        
        try:
            with open(file_path, "rb") as audio:
                await self._app.bot.send_voice(
                    chat_id=chat_id,
                    voice=audio,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send voice: {e}")
            return False
    
    async def send_photo(self, chat_id: int, file_path: str, caption: str = None) -> bool:
        """
        Send photo.
        
        Args:
            chat_id: Telegram chat ID
            file_path: Path to image file
            caption: Optional caption
            
        Returns:
            True if successful
        """
        if not self._app:
            return False
        
        try:
            with open(file_path, "rb") as photo:
                await self._app.bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=caption,
                )
            return True
        except Exception as e:
            logger.error(f"Failed to send photo: {e}")
            return False


async def run_bot():
    """Run the Telegram bot."""
    setup_logging()
    config = get_config()
    
    bot = TelegramBot(config)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(run_bot())