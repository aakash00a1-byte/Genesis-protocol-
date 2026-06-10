"""Genesis Protocol - Callback Handler

Handles inline button callbacks from Telegram.
"""

from telegram import Update
from telegram.ext import ContextTypes

from genesis_protocol.bot.telegram_bot import TelegramBot
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.handlers.callback")


class CallbackHandler:
    """
    Handles callback queries from inline keyboards.
    """
    
    def __init__(self, bot: TelegramBot):
        """Initialize callback handler."""
        self.bot = bot
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle callback query.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        query = update.callback_query
        
        if not query:
            return
        
        # Answer callback immediately
        await query.answer()
        
        data = query.data
        chat_id = query.message.chat_id
        user_id = query.from_user.id
        
        logger.info(f"Callback: {data}", user_id=user_id)
        
        # Route callback
        handlers = {
            "settings": self._handle_settings,
            "help": self._handle_help,
            "stats": self._handle_stats,
            "reset": self._handle_reset,
            "model_menu": self._handle_model_menu,
            "debug_toggle": self._handle_debug_toggle,
        }
        
        # Handle model switches
        if data.startswith("model_"):
            await self._handle_model_switch(update, data)
            return
        
        # Route to handler
        handler = handlers.get(data)
        if handler:
            await handler(update)
    
    async def _handle_settings(self, update: Update):
        """Handle settings callback."""
        text = """
⚙️ *Settings Menu*

*Available Options:*
• Response style (concise/detailed)
• AI provider selection
• Feature toggles

Use /settings for full configuration.
"""
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    
    async def _handle_help(self, update: Update):
        """Handle help callback."""
        text = """
📚 *Quick Help*

*Commands:*
/start - Start bot
/help - Full help
/settings - Configure
/stats - View stats
/reset - Clear history

*Send:*
• Text for AI responses
• Voice for transcription
• Images for analysis
"""
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    
    async def _handle_stats(self, update: Update):
        """Handle stats callback."""
        text = """
📊 *Your Stats*

Messages: 0
Tokens: 0
AI Calls: 0

Use /stats for full details.
"""
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    
    async def _handle_reset(self, update: Update):
        """Handle reset callback."""
        from genesis_protocol.memory.conversation_memory import ConversationMemory
        
        memory = ConversationMemory()
        chat_id = update.callback_query.message.chat_id
        
        await memory.clear_conversation(chat_id)
        
        await update.callback_query.edit_message_text(
            "✅ *Conversation Reset*\n\nFresh start!",
            parse_mode="Markdown"
        )
    
    async def _handle_model_menu(self, update: Update):
        """Handle model menu callback."""
        text = """
🤖 *Select AI Model*

• Groq (Fastest) - /model groq
• OpenAI (High Quality) - /model openai
• Gemini (Large Context) - /model gemini
"""
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    
    async def _handle_model_switch(self, update: Update, data: str):
        """Handle model switch callback."""
        model = data.replace("model_", "")
        
        await update.callback_query.edit_message_text(
            f"✅ *Model: {model}*\n\nUse /model {model} to activate.",
            parse_mode="Markdown"
        )
    
    async def _handle_debug_toggle(self, update: Update):
        """Handle debug toggle callback."""
        await update.callback_query.edit_message_text(
            "🔧 Debug mode: Toggle functionality coming soon",
            parse_mode="Markdown"
        )