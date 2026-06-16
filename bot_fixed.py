#!/usr/bin/env python3
"""
Genesis Protocol - Fixed Telegram Bot Runner
With better error handling and debug output.
"""

import sys
import os
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

import asyncio
import logging

# Setup detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)-8s] %(message)s',
    handlers=[
        logging.FileHandler('/tmp/bot_debug.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    logger.info("=" * 60)
    logger.info("📱 STARTING GENESIS PROTOCOL BOT (DEBUG MODE)")
    logger.info("=" * 60)
    
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
        
        from genesis_protocol.config import get_config
        from genesis_protocol.utils.logger import setup_logging
        
        # Setup app logging
        setup_logging()
        
        config = get_config()
        logger.info(f"Config loaded - Bot token: {config.telegram.bot_token[:15]}...")
        
        # Create application
        app = Application.builder().token(config.telegram.bot_token).build()
        logger.info("Telegram application created")
        
        # Command handlers
        async def start_handler(update: Update, context):
            logger.info(f"START command from user {update.effective_user.id}")
            await update.message.reply_text(
                "👋 *Genesis Protocol Bot*\n\n"
                "I am an autonomous AI assistant!\n\n"
                "Available commands:\n"
                "/start - Start bot\n"
                "/help - Show help\n"
                "/hi - Say hello\n"
                "/model - Switch AI model\n"
                "/stats - Show stats\n"
                "/reset - Reset conversation\n\n"
                "Just send me a message and I'll respond!",
                parse_mode="Markdown"
            )
        
        async def help_handler(update: Update, context):
            logger.info(f"HELP command from user {update.effective_user.id}")
            await update.message.reply_text(
                "📚 *Help*\n\n"
                "I can help you with:\n"
                "• Answering questions\n"
                "• Writing code\n"
                "• Creating stories\n"
                "• Generating images\n"
                "• And much more!\n\n"
                "Just type your message and I'll respond!",
                parse_mode="Markdown"
            )
        
        async def hi_handler(update: Update, context):
            logger.info(f"HI command from user {update.effective_user.id}")
            name = update.effective_user.first_name
            await update.message.reply_text(f"👋 Hi {name}! Kaise ho? 🎉")
        
        async def echo_handler(update: Update, context):
            """Simple echo handler for testing."""
            user_id = update.effective_user.id
            chat_id = update.effective_chat.id
            text = update.message.text
            
            logger.info(f"ECHO: User {user_id} in chat {chat_id}: {text}")
            
            # Reply back
            await update.message.reply_text(
                f"✅ I received your message!\n\n"
                f"You said: {text}\n\n"
                f"Let me think of a response...",
                parse_mode="Markdown"
            )
            
            # Now try to get AI response
            try:
                from genesis_protocol.ai.provider_chain import get_provider_chain
                from genesis_protocol.ai.prompts import get_system_prompt
                
                logger.info("Getting AI response...")
                
                ai_chain = get_provider_chain()
                
                messages = [
                    {"role": "system", "content": "You are a helpful AI assistant. Keep responses short and friendly."},
                    {"role": "user", "content": text}
                ]
                
                result = await ai_chain.call(messages=messages, user_input=text)
                
                if result.success:
                    logger.info(f"AI Response: {result.response.content[:100]}...")
                    await update.message.reply_text(
                        f"🤖 *AI Response:*\n\n{result.response.content}",
                        parse_mode="Markdown"
                    )
                else:
                    logger.error(f"AI failed: {result.error}")
                    await update.message.reply_text(
                        "❌ AI service is having issues. Please try again later.",
                        parse_mode="Markdown"
                    )
                    
            except Exception as e:
                logger.error(f"Error getting AI response: {e}")
                import traceback
                traceback.print_exc()
        
        # Register handlers
        app.add_handler(CommandHandler("start", start_handler))
        app.add_handler(CommandHandler("help", help_handler))
        app.add_handler(CommandHandler("hi", hi_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))
        
        logger.info("Handlers registered")
        logger.info("Starting polling...")
        
        # Start with webhook or polling
        print()
        print("=" * 60)
        print("📱 BOT IS READY!")
        print("=" * 60)
        print()
        print("Go to Telegram and send:")
        print("  /start - To start")
        print("  /hi - To say hello")
        print("  Any message - To chat")
        print()
        print("=" * 60)
        
        # Start polling
        await app.run_polling(drop_pending_updates=True)
        
    except Exception as e:
        logger.error(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
