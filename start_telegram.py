#!/usr/bin/env python3
"""
Genesis Protocol - Telegram Bot with Threading
Works around Python 3.13 asyncio issues
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import threading
import time

def run_bot():
    import asyncio
    from telegram.ext import Application, CommandHandler, MessageHandler, filters
    from telegram import Update
    from genesis_protocol.config import get_config
    from genesis_protocol.ai.provider_chain import get_provider_chain
    
    config = get_config()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print("=" * 60)
    print("📱 GENESIS PROTOCOL BOT - STARTING")
    print("=" * 60)
    print()
    
    app = Application.builder().token(config.telegram.bot_token).build()
    
    async def start(update, context):
        await update.message.reply_text(
            "👋 *Genesis Protocol Bot*\n\n"
            "✅ Bot is online!\n"
            "Send me any message and I'll respond!\n\n"
            "Commands:\n"
            "/start - Start\n"
            "/hi - Say hello",
            parse_mode="Markdown"
        )
    
    async def hi(update, context):
        name = update.effective_user.first_name
        await update.message.reply_text(f"👋 Hi {name}! Kaise ho? 🎉")
    
    async def echo(update, context):
        text = update.message.text
        print(f"📨 Message: {text}")
        
        await update.message.reply_text(f"✅ Received: {text}\n\n🤖 Processing...")
        
        try:
            ai = get_provider_chain()
            result = await ai.call(
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant. Keep responses short."},
                    {"role": "user", "content": text}
                ],
                user_input=text
            )
            
            if result.success:
                response = result.response.content[:4000]  # Telegram limit
                await update.message.reply_text(f"🤖 *Response:*\n\n{response}", parse_mode="Markdown")
            else:
                await update.message.reply_text(f"❌ AI Error: {result.error}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)[:500]}")
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hi", hi))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    
    print("✅ Handlers registered")
    print("📱 Bot ready! Go to @Genesis_autonomousbot")
    print()
    
    app.run_polling(drop_pending_updates=True, close_loop=False)

if __name__ == "__main__":
    thread = threading.Thread(target=run_bot, daemon=True)
    thread.start()
    
    print("Bot thread started. Press Ctrl+C to stop.")
    while True:
        time.sleep(1)
