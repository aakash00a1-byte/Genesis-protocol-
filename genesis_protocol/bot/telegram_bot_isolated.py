"""Genesis Protocol - Telegram Bot with Channel Isolation

Telegram integration with strict channel isolation:
- Admin-only mode (optional)
- Admin alerts for system events
- No cross-channel message leakage
- Independent from web platform
"""

import os
import sys
import logging
from typing import Optional, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler
)

from genesis_protocol.config import get_config
from genesis_protocol.core.channel import Channel, get_channel_isolation
from genesis_protocol.core.admin_alerts import get_admin_alerts, AlertLevel, AlertType
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.telegram_isolated")


class TelegramBotIsolated:
    """
    Telegram bot with channel isolation.
    
    In admin-only mode, only the admin receives messages.
    Admin receives system alerts automatically.
    """
    
    def __init__(self):
        """Initialize isolated Telegram bot."""
        self.config = get_config()
        self.channel_isolation = get_channel_isolation()
        self.admin_alerts = get_admin_alerts()
        
        # Check if Telegram is enabled
        self.enabled = self.config.telegram_enabled
        self.admin_only = self.config.telegram_admin_only
        self.admin_chat_id = self.config.telegram_admin_chat_id
        
        # Initialize app
        self.app: Optional[Application] = None
        
        if self.enabled:
            self._setup_bot()
            self._setup_admin_alerts()
        else:
            logger.info("Telegram integration disabled")
    
    def _setup_bot(self):
        """Setup Telegram bot."""
        if not self.config.telegram.bot_token:
            logger.warning("Telegram bot token not configured")
            self.enabled = False
            return
        
        self.app = Application.builder().token(self.config.telegram.bot_token).build()
        
        # Add handlers
        self.app.add_handler(CommandHandler("start", self._handle_start))
        self.app.add_handler(CommandHandler("help", self._handle_help))
        self.app.add_handler(CommandHandler("status", self._handle_status))
        self.app.add_handler(CommandHandler("admin", self._handle_admin))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        
        # Set admin chat ID if not configured
        if not self.admin_chat_id:
            logger.warning("TELEGRAM_ADMIN_CHAT_ID not set - admin alerts disabled")
        
        logger.info("Telegram bot initialized (isolated mode)")
    
    def _setup_admin_alerts(self):
        """Setup admin alert system."""
        if self.admin_chat_id:
            self.admin_alerts.set_admin_chat_id(self.admin_chat_id)
            self.admin_alerts.register_sender(self._send_telegram_message)
            self.admin_alerts.enable()
            logger.info(f"Admin alerts enabled for chat ID: {self.admin_chat_id}")
    
    async def _send_telegram_message(self, chat_id: int, text: str):
        """Send message to Telegram (internal use for alerts)."""
        if self.app and chat_id:
            try:
                await self.app.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
    
    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        chat_id = update.effective_chat.id
        
        # Set channel isolation
        self.channel_isolation.set_channel(Channel.TELEGRAM)
        self.channel_isolation.log_channel_activity(Channel.TELEGRAM, "start", f"Chat {chat_id}")
        
        # Check admin-only mode
        if self.admin_only and chat_id != self.admin_chat_id:
            await update.message.reply_text(
                "🔒 *Genesis Telegram - Admin Mode*\n\n"
                "This bot is currently in admin-only mode.\n"
                "Please use the web platform for general assistance.\n\n"
                "🌐 [Open Genesis Web](https://your-domain.com)",
                parse_mode='Markdown'
            )
            return
        
        welcome = """
⚡ *Genesis Protocol - Telegram Bot*

Welcome! I'm your autonomous AI assistant.

Available commands:
• /start - Show this message
• /help - Show help
• /status - System status
• /admin - Admin panel

Just send me a message to start chatting!
"""
        await update.message.reply_text(welcome, parse_mode='Markdown')
    
    async def _handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        chat_id = update.effective_chat.id
        
        # Check admin-only
        if self.admin_only and chat_id != self.admin_chat_id:
            return
        
        help_text = """
📚 *Help*

*Commands:*
• /start - Start the bot
• /help - Show this help
• /status - View system status
• /admin - Admin panel

*Usage:*
Simply type your question and I'll respond with the power of multi-LLM intelligence!

*Features:*
• Multi-model routing
• Web search
• Code execution
• Memory
• Autonomous mode
"""
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - Admin only."""
        chat_id = update.effective_chat.id
        
        # Check admin-only
        if self.admin_only and chat_id != self.admin_chat_id:
            return
        
        # Get system status
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        providers = chain.get_available_providers()
        
        status = f"""
🖥️ *System Status*

*Mode:* {'Admin-Only' if self.admin_only else 'Public'}

*Active Providers:*
"""
        for p in providers:
            status += f"• {p}\n"
        
        status += f"\n*Web Platform:* Active\n"
        status += f"*Channel:* TELEGRAM (isolated)"
        
        await update.message.reply_text(status, parse_mode='Markdown')
    
    async def _handle_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /admin command - Admin only."""
        chat_id = update.effective_chat.id
        
        if chat_id != self.admin_chat_id:
            await update.message.reply_text("🔒 Admin access required")
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("🔄 Reset Circuits", callback_data="admin_reset")],
            [InlineKeyboardButton("📋 View Logs", callback_data="admin_logs")],
            [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔧 *Admin Panel*\n\nSelect an option:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages."""
        chat_id = update.effective_chat.id
        user_message = update.message.text
        
        # Set channel isolation
        self.channel_isolation.set_channel(Channel.TELEGRAM)
        self.channel_isolation.log_channel_activity(
            Channel.TELEGRAM, "message", f"Chat {chat_id}: {user_message[:50]}"
        )
        
        # Check admin-only mode
        if self.admin_only and chat_id != self.admin_chat_id:
            await update.message.reply_text(
                "🔒 This bot is in admin-only mode. "
                "Please use the web platform for assistance.",
                parse_mode='Markdown'
            )
            return
        
        # Send typing indicator
        await update.message.chat.send_action("typing")
        
        try:
            # Process with Genesis Agent
            from genesis_protocol.ai.agent import get_genesis_agent
            
            agent = get_genesis_agent()
            result = await agent.process(
                user_message, 
                chat_id=chat_id, 
                user_id=chat_id
            )
            
            # Send response - ONLY to Telegram
            if result.success:
                await update.message.reply_text(
                    result.response[:4096],  # Telegram limit
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    "❌ An error occurred. Please try again."
                )
                
        except Exception as e:
            logger.error(f"Telegram message error: {e}")
            self.admin_alerts.alert_critical_error(
                f"Telegram message failed: {str(e)}",
                {"chat_id": str(chat_id)}
            )
            await update.message.reply_text("❌ An error occurred. Please try again.")
    
    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries."""
        query = update.callback_query
        
        if not query:
            return
        
        chat_id = query.message.chat.id
        
        # Admin only
        if chat_id != self.admin_chat_id:
            await query.answer("Admin access required")
            return
        
        await query.answer()
        
        data = query.data
        
        if data == "admin_stats":
            await self._send_admin_stats(query)
        elif data == "admin_reset":
            await self._reset_circuits(query)
        elif data == "admin_logs":
            await self._send_logs(query)
    
    async def _send_admin_stats(self, query):
        """Send admin statistics."""
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        chain = get_provider_chain()
        status = chain.get_status()
        
        stats = "*System Statistics*\n\n"
        for name, info in status.items():
            configured = "✅" if info.get("configured") else "❌"
            stats += f"{configured} {name}: {info.get('circuit_state', 'unknown')}\n"
        
        await query.edit_message_text(stats, parse_mode='Markdown')
    
    async def _reset_circuits(self, query):
        """Reset provider circuits."""
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        chain = get_provider_chain()
        chain.reset_all_circuits()
        
        await query.edit_message_text("✅ All circuits reset")
    
    async def _send_logs(self, query):
        """Send recent logs."""
        logs = self.channel_isolation.get_channel_history(limit=10)
        
        if not logs:
            await query.edit_message_text("No recent logs")
            return
        
        msg = "*Recent Activity*\n\n"
        for log in logs:
            msg += f"[{log['timestamp'][11:19]}] {log['channel']}: {log['action']}\n"
        
        await query.edit_message_text(msg, parse_mode='Markdown')
    
    def run(self):
        """Run the bot."""
        if not self.enabled:
            logger.info("Telegram bot disabled")
            return
        
        if not self.app:
            logger.error("Telegram bot not initialized")
            return
        
        logger.info("Starting Telegram bot (isolated mode)")
        
        # Send startup alert to admin
        self.admin_alerts.alert_deployment(
            "Telegram bot started",
            success=True,
            details={"mode": "admin_only" if self.admin_only else "public"}
        )
        
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


# Singleton
_telegram_bot: Optional[TelegramBotIsolated] = None


def get_telegram_bot() -> TelegramBotIsolated:
    """Get Telegram bot singleton."""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBotIsolated()
    return _telegram_bot


def run_telegram_bot():
    """Run Telegram bot."""
    bot = get_telegram_bot()
    bot.run()


if __name__ == '__main__':
    run_telegram_bot()