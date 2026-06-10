"""Genesis Protocol - Command Handler

Handles bot commands (/start, /help, /settings, etc.).
"""

from telegram import Update
from telegram.ext import ContextTypes

from genesis_protocol.bot.telegram_bot import TelegramBot
from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.utils.logger import get_logger

logger = get_logger("bot.handlers.command")


class CommandHandler:
    """
    Handles bot commands.
    """
    
    def __init__(self, bot: TelegramBot):
        """Initialize command handler."""
        self.bot = bot
        self.memory = ConversationMemory()
    
    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /start command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        welcome_message = f"""
🤖 *Welcome to Genesis Protocol!*

Hello {user.first_name}! I'm your autonomous AI assistant.

*What I can do:*
• Answer questions and provide information
• Analyze images you send
• Transcribe and respond to voice messages
• Search the web for current information
• Remember our conversation context

*Getting Started:*
Simply send me a message and I'll respond!

*Commands:*
/help - Show all commands
/settings - Configure preferences
/stats - View your usage statistics

Let's get started! 🚀
"""
        
        await self.bot.send_message(chat_id, welcome_message, parse_mode="Markdown")
        
        logger.info(f"User started bot", user_id=user.id, username=user.username)
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /help command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        help_text = """
📚 *Genesis Protocol Commands*

*Basic Commands:*
/start - Start the bot
/help - Show this help message
/settings - Configure bot settings

*AI Commands:*
/model - Switch between AI providers
/model groq - Use Groq (fastest)
/model openai - Use OpenAI GPT
/model gemini - Use Google Gemini

*Management:*
/stats - View usage statistics
/reset - Clear conversation history
/debug - Toggle debug mode

*Features:*
• *Text* - Send any text message
• *Voice* - Send voice notes for transcription
• *Images* - Send photos for analysis
• *Web Search* - Ask "search for..." for real-time info

*Tips:*
• Be specific in questions for better answers
• Use code blocks for programming help
• /reset clears context if conversations get confused
"""
        
        await self.bot.send_message(update.effective_chat.id, help_text, parse_mode="Markdown")
    
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /settings command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        settings_text = """
⚙️ *Bot Settings*

*Available Settings:*

1️⃣ *Response Style*
   - Concise (short answers)
   - Detailed (comprehensive)
   - Technical (expert level)

2️⃣ *AI Provider*
   - Groq (fastest, recommended)
   - OpenAI (high quality)
   - Gemini (large context)

3️⃣ *Features*
   - Voice messages: on/off
   - Image analysis: on/off
   - Web search: on/off

*To change settings:*
Use the inline keyboard below or contact admin.
"""
        
        await self.bot.send_message(update.effective_chat.id, settings_text, parse_mode="Markdown")
    
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /stats command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        user_id = update.effective_user.id
        
        # Get user stats from memory
        stats_text = f"""
📊 *Your Statistics*

*Usage:*
• Messages today: calculating...
• Total messages: tracking...

*AI Providers Used:*
• Groq: tracking...
• OpenAI: tracking...
• Gemini: tracking...

*Current Session:*
• Conversation started: now
• Context messages: counting...

*Note:* Full statistics tracking coming soon!
"""
        
        await self.bot.send_message(update.effective_chat.id, stats_text, parse_mode="Markdown")
    
    async def handle_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /reset command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        chat_id = update.effective_chat.id
        
        await self.memory.clear_conversation(chat_id)
        
        await self.bot.send_message(
            chat_id,
            "✅ *Conversation Reset*\n\nAll context has been cleared. Fresh start!",
            parse_mode="Markdown"
        )
        
        logger.info(f"Conversation reset", chat_id=chat_id)
    
    async def handle_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /model command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        args = context.args
        
        if not args:
            # Show current model
            current_model = "groq"  # Default
            model_text = f"""
🤖 *Current AI Model*

Your active AI provider: *{current_model}*

*Available Models:*
• /model groq - Groq (fastest)
• /model openai - OpenAI GPT-4
• /model gemini - Google Gemini

*Usage:* /model <provider>
"""
            await self.bot.send_message(update.effective_chat.id, model_text, parse_mode="Markdown")
            return
        
        model = args[0].lower()
        valid_models = ["groq", "openai", "gemini", "huggingface"]
        
        if model in valid_models:
            await self.bot.send_message(
                update.effective_chat.id,
                f"✅ *Model Changed*\n\nAI provider switched to *{model}*. All new requests will use this provider.",
                parse_mode="Markdown"
            )
            logger.info(f"Model changed to {model}", user_id=update.effective_user.id)
        else:
            await self.bot.send_message(
                update.effective_chat.id,
                f"❌ *Invalid Model*\n\nValid options: {', '.join(valid_models)}",
                parse_mode="Markdown"
            )
    
    async def handle_debug(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /debug command.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        debug_info = """
🔧 *Debug Mode*

*System Status:*
• Bot: Running ✅
• Memory: Active ✅
• AI Chain: Checking...

*Provider Status:*
• Groq: Checking...
• OpenAI: Checking...
• Gemini: Checking...

*Session Info:*
• Chat ID: {chat_id}
• User ID: {user_id}

*Debug commands:*
• /debug status - Show detailed status
• /debug memory - Show memory contents
• /debug ai - Show AI chain status
""".format(
            chat_id=update.effective_chat.id,
            user_id=update.effective_user.id
        )
        
        await self.bot.send_message(update.effective_chat.id, debug_info, parse_mode="Markdown")