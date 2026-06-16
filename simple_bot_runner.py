#!/usr/bin/env python3
"""
Genesis Protocol - Simple Telegram Bot Runner
Uses threading to avoid asyncio event loop issues.
"""

import sys
import threading
import asyncio
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from genesis_protocol.bot.telegram_bot import TelegramBot

def run_bot():
    """Run the bot in a separate thread with its own event loop."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot = TelegramBot()
        loop.run_until_complete(bot.initialize())
        
        print("=" * 60)
        print("📱 GENESIS PROTOCOL - TELEGRAM BOT RUNNING")
        print("=" * 60)
        print()
        print("✅ Bot is online!")
        print("📱 Go to Telegram and message @Genesis_autonomousbot")
        print("   Send /start to begin")
        print()
        print("Commands:")
        print("   /start - Start bot")
        print("   /help - Show help")
        print("   /model - Switch AI model")
        print("   /stats - Show stats")
        print("   /reset - Reset conversation")
        print()
        print("-" * 60)
        print()
        
        # Start polling
        bot._app.run_polling(drop_pending_updates=True)
        
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            loop.close()
        except:
            pass

if __name__ == "__main__":
    run_bot()
