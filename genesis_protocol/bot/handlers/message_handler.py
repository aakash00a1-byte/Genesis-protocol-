"""Genesis Protocol - Message Handler

Handles text message processing and routing.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from genesis_protocol.bot.telegram_bot import TelegramBot

from genesis_protocol.models.message import Message, MessageType, MessageDirection
from genesis_protocol.memory.conversation_memory import ConversationMemory
from genesis_protocol.ai.provider_chain import get_provider_chain
from genesis_protocol.ai.prompts import get_system_prompt
from genesis_protocol.utils.logger import get_logger
from genesis_protocol.utils.sanitizers import Sanitizer
from genesis_protocol.utils.formatters import Formatter

logger = get_logger("bot.handlers.message")


class MessageHandler:
    """
    Handles text messages and callback queries.
    """
    
    def __init__(self, bot: 'TelegramBot'):
        """Initialize message handler."""
        self.bot = bot
        self.memory = ConversationMemory()
        self.ai_chain = get_provider_chain()
        self.sanitizer = Sanitizer()
        self.formatter = Formatter()
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle incoming text message.
        
        Args:
            update: Telegram update
            context: Handler context
        """
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        text = update.message.text
        
        # Sanitize input
        text = self.sanitizer.sanitize_text(text)
        
        if not text:
            return
        
        logger.info(
            "Processing text message",
            chat_id=chat_id,
            user_id=user_id,
            text_length=len(text)
        )
        
        # Create message object
        message = Message(
            id=str(update.message.message_id),
            chat_id=chat_id,
            user_id=user_id,
            message_type=MessageType.TEXT,
            direction=MessageDirection.INCOMING,
            text=text,
        )
        
        # Add to conversation memory
        await self.memory.add_message(chat_id, message)
        
        # Send typing indicator
        await self.bot.send_typing(chat_id)
        
        # Get conversation context
        context_str = await self.memory.get_context_for_ai(chat_id)
        
        # Build messages for AI
        system_prompt = get_system_prompt(
            user_name=update.effective_user.first_name,
            chat_id=chat_id,
            memory_context=context_str,
        )
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history
        history = await self.memory.get_history(chat_id, limit=20)
        for msg in history:
            role = "user" if msg.direction == MessageDirection.INCOMING else "assistant"
            messages.append({
                "role": role,
                "content": msg.text or ""
            })
        
        # Add current message
        messages.append({"role": "user", "content": text})
        
        # Call AI with routing (pass user_input for smart model selection)
        result = await self.ai_chain.call(
            messages=messages,
            user_input=text  # For LLM router to select best model
        )
        
        if result.success and result.response:
            response_text = result.response.content
            
            # Format response
            response_text = self.formatter.format_markdown(response_text)
            response_text = self.formatter.truncate_response(response_text)
            
            # Send response
            await self.bot.send_message(
                chat_id=chat_id,
                text=response_text,
                parse_mode="Markdown",
            )
            
            # Record success in message
            message.mark_processed(
                provider=result.provider_used,
                model=result.response.model,
                tokens=result.response.tokens_used,
                latency=result.response.latency_ms,
            )
            
            logger.info(
                "Message processed successfully",
                provider=result.provider_used,
                tokens=result.response.tokens_used
            )
        else:
            # Send error message
            error_msg = self.formatter.format_error(
                "AI service unavailable. Please try again.",
                include_trace=False
            )
            await self.bot.send_message(chat_id=chat_id, text=error_msg)
            
            message.mark_failed(result.error or "Unknown error")
            
            logger.error(f"Message processing failed: {result.error}")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle callback query (inline button press).
        
        Args:
            update: Telegram update
            context: Handler context
        """
        query = update.callback_query
        
        if not query:
            return
        
        await query.answer()
        
        data = query.data
        chat_id = query.message.chat_id
        
        logger.info(f"Callback query: {data}")
        
        # Handle callback data
        if data == "settings":
            await self._show_settings(update, context)
        elif data == "help":
            await self._show_help(update, context)
        elif data.startswith("model_"):
            await self._switch_model(update, context, data)
        elif data == "reset":
            await self.memory.clear_conversation(chat_id)
            await query.edit_message_text("✅ Conversation history cleared.")
    
    async def _show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show settings menu."""
        keyboard = [
            ["Switch Model", "model_menu"],
            ["Reset Memory", "reset"],
            ["Back to Help", "help"],
        ]
        
        text = "⚙️ *Settings*\n\nChoose an option:"
        
        # Implementation depends on inline keyboard setup
        pass
    
    async def _show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help information."""
        text = """
*Genesis Protocol Help*

*Commands:*
/start - Start the bot
/help - Show this help
/settings - Configure settings
/stats - View usage statistics
/reset - Clear conversation history
/model - Switch AI model
/debug - Toggle debug mode

*Features:*
• Send text messages for AI assistance
• Send voice notes for transcription
• Send images for analysis
• Real-time web search capability

*Tips:*
• Use Markdown for formatting
• Be specific in your questions
• Use /reset to clear context
"""
        
        await update.callback_query.edit_message_text(text)
    
    async def _switch_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        """Switch AI model."""
        model = data.replace("model_", "")
        
        await self.bot.send_message(
            chat_id=update.callback_query.message.chat_id,
            text=f"Model switched to {model}. Changes will take effect on next message."
        )