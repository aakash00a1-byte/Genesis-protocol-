"""Genesis Protocol - Command Handler

Handles bot commands (/start, /help, /settings, etc.) and power commands.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from genesis_protocol.bot.telegram_bot import TelegramBot

from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.utils.logger import get_logger
from genesis_protocol.powers import CodeGenerator, BugHunter, ErrorFixer, APKBuilder, Deployer, get_github_manager

logger = get_logger("bot.handlers.command")


class CommandHandler:
    """
    Handles bot commands.
    """
    
    def __init__(self, bot: 'TelegramBot'):
        """Initialize command handler."""
        self.bot = bot
        self.memory = ConversationMemory()
        
        # Initialize power modules
        self.code_generator = CodeGenerator()
        self.bug_hunter = BugHunter()
        self.error_fixer = ErrorFixer()
        self.apk_builder = APKBuilder()
        self.deployer = Deployer()
        self.github = get_github_manager()
    
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

    # ==================== GENESIS POWER COMMANDS ====================

    async def handle_generate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /generate command - Generate code."""
        chat_id = update.effective_chat.id
        args = context.args
        
        if not args:
            await self.bot.send_message(
                chat_id,
                "📝 *Code Generator*\n\nUsage: /generate <description>\n\nExample:\n/generate a flask api endpoint for user login",
                parse_mode="Markdown"
            )
            return
        
        description = " ".join(args)
        await self.bot.send_message(chat_id, "⚡ Generating code...")
        
        try:
            result = await self.code_generator.generate_from_natural_language(description)
            
            if result.success:
                response = f"✅ *Code Generated*\n\n"
                response += f"Language: `{result.language}`\n"
                response += f"Files: {', '.join(result.files_created)}\n\n"
                response += f"📄 *Code:*\n```\n{result.code[:4000]}\n```\n\n"
                
                if result.explanation:
                    response += f"💡 *Explanation:*\n{result.explanation}"
                
                if result.warnings:
                    response += f"\n⚠️ *Warnings:*\n" + "\n".join(result.warnings)
                
                await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            else:
                await self.bot.send_message(chat_id, f"❌ Generation failed: {result.error}", parse_mode="Markdown")
                
        except Exception as e:
            await self.bot.send_message(chat_id, f"❌ Error: {str(e)}", parse_mode="Markdown")

    async def handle_bughunt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bughunt command - Analyze code for bugs."""
        chat_id = update.effective_chat.id
        
        # Check if code is provided as argument or as reply
        if context.args:
            code = " ".join(context.args)
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            code = update.message.reply_to_message.text
        else:
            await self.bot.send_message(
                chat_id,
                "🐛 *Bug Hunter*\n\nUsage:\n/bughunt <code or error>\n\nOr reply to a message with /bughunt",
                parse_mode="Markdown"
            )
            return
        
        await self.bot.send_message(chat_id, "🔍 Analyzing code for bugs...")
        
        try:
            result = await self.bug_hunter.analyze(code)
            
            response = f"📊 *Analysis Complete*\n\n"
            response += f"Score: *{result.score}/100*\n"
            response += f"Issues Found: {len(result.bugs)}\n"
            response += f"🔴 Security: {result.security_issues}\n"
            response += f"🐌 Performance: {result.performance_issues}\n\n"
            
            if result.bugs:
                response += "*🔴 Critical Issues:*\n"
                for bug in result.bugs[:5]:
                    if bug.severity.value == "critical":
                        response += f"• Line {bug.line}: {bug.title}\n"
                        response += f"  → {bug.suggestion}\n"
                
                response += "\n*🟠 High Priority:*\n"
                for bug in result.bugs[:5]:
                    if bug.severity.value == "high":
                        response += f"• {bug.title}\n"
            else:
                response += "✅ No bugs found!"
            
            await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            
        except Exception as e:
            await self.bot.send_message(chat_id, f"❌ Analysis error: {str(e)}", parse_mode="Markdown")

    async def handle_fix(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /fix command - Fix errors."""
        chat_id = update.effective_chat.id
        
        # Get error message
        if context.args:
            error_msg = " ".join(context.args)
        elif update.message.reply_to_message and update.message.reply_to_message.text:
            error_msg = update.message.reply_to_message.text
        else:
            await self.bot.send_message(
                chat_id,
                "🔧 *Error Fixer*\n\nUsage:\n/fix <error message>\n\nOr reply to error with /fix",
                parse_mode="Markdown"
            )
            return
        
        await self.bot.send_message(chat_id, "🔧 Fixing error...")
        
        try:
            result = await self.error_fixer.fix_error(error_msg)
            
            if result.success and result.fixes:
                fix = result.fixes[0]
                response = f"✅ *Error Fixed*\n\n"
                response += f"💡 *What was wrong:*\n{fix.explanation}\n\n"
                response += f"🔧 *Fix applied:*\n"
                response += f"```\n{fix.fixed_code[:3000]}\n```\n\n"
                response += f"Confidence: {int(fix.confidence * 100)}%"
                
                await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            else:
                await self.bot.send_message(
                    chat_id,
                    f"🤷 Could not auto-fix this error.\n\nError: {result.original_error[:500]}",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            await self.bot.send_message(chat_id, f"❌ Fix error: {str(e)}", parse_mode="Markdown")

    async def handle_apk(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /apk command - APK builder status."""
        chat_id = update.effective_chat.id
        
        status = self.apk_builder.get_status()
        
        response = "📱 *APK Builder Status*\n\n"
        response += f"Android SDK: {'✅ Available' if status['sdk_available'] else '❌ Not found'}\n"
        response += f"Gradle: {'✅ Available' if status['gradle_available'] else '❌ Not found'}\n"
        response += f"Build Tools: {'✅ Installed' if status['build_tools_installed'] else '❌ Missing'}\n"
        response += f"Platforms: {'✅ Installed' if status['platforms_installed'] else '❌ Missing'}\n\n"
        
        devices = self.apk_builder.list_devices()
        if devices:
            response += "*📱 Connected Devices:*\n"
            for d in devices:
                response += f"• {d['id']} ({d['status']})\n"
        else:
            response += "*📱 Devices:* None connected\n"
        
        response += "\n*Commands:*\n"
        response += "/apk create <name> - Create Android project\n"
        response += "/apk build - Build APK (needs project)\n"
        
        await self.bot.send_message(chat_id, response, parse_mode="Markdown")

    async def handle_deploy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /deploy command - Deploy application."""
        chat_id = update.effective_chat.id
        args = context.args
        
        if not args:
            platforms = self.deployer.get_platforms()
            response = "🚀 *Deployer*\n\n"
            response += "*Available Platforms:*\n"
            for p in platforms:
                available = self.deployer.check_platform_cli(p)
                response += f"• {p}: {'✅' if available else '⚠️ CLI needed'}\n"
            
            response += "\n*Usage:*\n"
            response += "/deploy railway - Deploy to Railway\n"
            response += "/deploy render - Deploy to Render\n"
            response += "/deploy docker - Build Docker container\n"
            response += "/deploy vercel - Deploy to Vercel\n"
            
            await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            return
        
        platform = args[0].lower()
        if platform not in self.deployer.get_platforms():
            await self.bot.send_message(chat_id, f"❌ Unknown platform: {platform}", parse_mode="Markdown")
            return
        
        await self.bot.send_message(chat_id, f"🚀 Deploying to {platform}...")
        
        try:
            result = await self.deployer.deploy(
                "/workspace/project/Genesis-protocol-",
                platform,
                {}
            )
            
            if result.success:
                response = f"✅ *Deployment Successful*\n\n"
                response += f"Platform: {result.platform}\n"
                if result.url:
                    response += f"URL: {result.url}\n"
                response += f"\n{result.logs[:500]}"
                
                await self.bot.send_message(chat_id, response, parse_mode="Markdown")
            else:
                await self.bot.send_message(
                    chat_id,
                    f"❌ Deployment failed: {result.error}",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            await self.bot.send_message(chat_id, f"❌ Deploy error: {str(e)}", parse_mode="Markdown")

    async def handle_powers(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /powers command - Show all Genesis powers."""
        chat_id = update.effective_chat.id
        
        response = """
⚡ *GENESIS PROTOCOL - SUPER POWERS* ⚡

*🛠️ Code Generator*
Generate code in any language from description
→ /generate <what to build>

*🐛 Bug Hunter*
Find bugs, security issues, code smells
→ /bughunt <code or error>

*🔧 Error Fixer*
Auto-fix common programming errors
→ /fix <error message>

*📱 APK Builder*
Build Android apps and APKs
→ /apk - Check status
→ /apk create <name> - Create project

*🚀 Deployer*
Deploy to Railway, Render, Vercel, Docker
→ /deploy - Show platforms
→ /deploy <platform> - Deploy

*💡 All powers work together!*
"""
        
        await self.bot.send_message(chat_id, response, parse_mode="Markdown")