#!/usr/bin/env python3
"""
Genesis Protocol - Simple Telegram Bot
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

if __name__ == "__main__":
    from telegram.ext import Application
    from telegram import Update
    from telegram.ext import CommandHandler, MessageHandler, filters
    from genesis_protocol.config import get_config
    
    config = get_config()
    
    print("=" * 60)
    print("📱 GENESIS PROTOCOL BOT")
    print("=" * 60)
    print()
    
    # Create app
    app = Application.builder().token(config.telegram.bot_token).build()
    
    # Handlers
    async def start(update, context):
        await update.message.reply_text(
            "👋 *Genesis Protocol Bot*\n\n"
            "Bot is online!\n\n"
            "Send me any message!",
            parse_mode="Markdown"
        )
    
    async def hi(update, context):
        name = update.effective_user.first_name
        await update.message.reply_text(f"👋 Hi {name}! Kaise ho?")
    
    async def echo(update, context):
        text = update.message.text
        print(f"Message received: {text}")
        await update.message.reply_text(f"✅ Got: {text}\n\nThinking...")
        
        # Get AI response
        try:
            from genesis_protocol.ai.provider_chain import get_provider_chain
            ai = get_provider_chain()
            result = await ai.call(
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant."},
                    {"role": "user", "content": text}
                ],
                user_input=text
            )
            if result.success:
                await update.message.reply_text(f"🤖 {result.response.content}", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ AI error")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:200]}")
    
    # Register
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hi", hi))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ Bot configured!")
    print()
    print("📱 Go to Telegram: @Genesis_autonomousbot")
    print()
    print("=" * 60)
    print()
    
    # Run
    app.run_polling(drop_pending_updates=True)
