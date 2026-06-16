#!/usr/bin/env python3
"""Genesis Protocol - Telegram Bot Runner"""

import sys
import asyncio
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from genesis_protocol.bot.telegram_bot import TelegramBot
from genesis_protocol.config import get_config

def main():
    print("="*60)
    print("📱 GENESIS PROTOCOL - TELEGRAM BOT")
    print("="*60)
    print()
    print("Starting bot...")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        # Create new event loop for telegram
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot = TelegramBot()
        loop.run_until_complete(bot.initialize())
        
        print("✅ Bot initialized!")
        print("📡 Bot is now running...")
        print()
        print("Go to Telegram and send /start to your bot!")
        print()
        
        # Run polling
        loop.run_until_complete(bot._app.run_polling(allowed_updates=None))
        
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user")
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
    main()
