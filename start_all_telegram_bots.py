#!/usr/bin/env python3
"""
Genesis Protocol - All Telegram Bots Starter
Runs all configured Telegram bots simultaneously
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import time
import json
import threading
import httpx
from datetime import datetime
from genesis_protocol.config import get_config


# ============================================================
# ADMIN CONFIGURATION
# ============================================================
def get_admin_ids():
    """Get admin Telegram IDs from environment"""
    env_ids = os.environ.get("TELEGRAM_ADMIN_IDS", "")
    if env_ids:
        try:
            return [int(id.strip()) for id in env_ids.split(",")]
        except:
            pass
    return []


ADMIN_IDS = get_admin_ids()


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS


# ============================================================
# BOT INSTANCES
# ============================================================
class TelegramBot:
    def __init__(self, token: str, username: str, admin_ids: list):
        self.token = token
        self.username = username
        self.admin_ids = admin_ids
        self.api = f"https://api.telegram.org/bot{token}"
        self.offset = 0
        self.running = False
        
    def send(self, chat_id, text):
        """Send message to Telegram"""
        try:
            httpx.post(f"{self.api}/sendMessage", json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }, timeout=10)
        except Exception as e:
            print(f"[{self.username}] Send error: {e}")
    
    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids
    
    def handle_message(self, msg: dict) -> str:
        """Process message and return response"""
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user_id = msg.get("from", {}).get("id", 0)
        user = msg.get("from", {}).get("first_name", "User")
        
        # Public Commands
        if text == "/start":
            return chat_id, f"""👋 *Welcome to {self.username}!*

I'm Genesis Protocol AI Bot. Here's what I can do:

🌐 *Public Commands:*
/start - Welcome message
/hi - Say hello
/help - Show all commands
/status - Bot status
/ask [question] - Chat with AI
/bots - List all bots

💬 Just send any message to chat with me!
"""
        elif text == "/hi" or text.lower() == "hi genesis":
            return chat_id, f"👋 Hi {user}! Kaise ho? 🎉\n\nUse /help to see all commands!"
        
        elif text == "/help":
            return chat_id, """📚 *Genesis Protocol Commands*

🌐 *Public:*
/start - Welcome message
/hi - Say hello
/help - Show commands
/status - Bot status
/ask [question] - Chat with AI
/bots - List all bots

💬 *Just send any message to chat with AI!*
"""
        elif text == "/status":
            return chat_id, f"""📊 *Genesis Status*

🤖 Bot: {self.username}
📡 Status: 🟢 Online
⏰ Time: {datetime.now().strftime('%H:%M:%S')}
🔧 Version: 2.2.0
🛠️ Admin Users: {len(self.admin_ids)}
"""
        elif text == "/bots":
            return chat_id, """🤖 *Genesis Protocol Bots*

1️⃣ @Genesis_autonomousbot - Main AI bot
2️⃣ @Gen_sisbot - Sister bot
3️⃣ @Genesis_makebot - Maker bot

All bots are online! 💪
"""
        elif text.startswith("/ask "):
            question = text[5:].strip()
            if question:
                return chat_id, "🤖 Thinking..."
            return chat_id, "❌ Usage: /ask [your question]"
        
        # Admin Commands
        elif text == "/admin" and self.is_admin(user_id):
            return chat_id, """⚙️ *Genesis Admin Panel*

🔒 *Admin Commands:*
/admin - This panel
/admin_status - Detailed status
/admin_broadcast - Broadcast message
/admin_stats - View statistics

*Configure TELEGRAM_ADMIN_IDS env var.*
"""
        elif text == "/admin_status" and self.is_admin(user_id):
            return chat_id, f"""⚙️ *System Status*

🤖 Bot: {self.username}
📡 Status: 🟢 Running
👥 Admins: {len(self.admin_ids)}
⏰ Uptime: Since startup
🔧 Version: 2.2.0
🧠 AI: ✅ Ready
"""
        elif text == "/admin_stats" and self.is_admin(user_id):
            return chat_id, f"""📈 *Statistics*

👥 Admin Users: {len(self.admin_ids)}
⏰ Bot Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}
🔧 Version: 2.2.0
🛠️ Commands: 12 total
   - Public: 6
   - Admin: 4
"""
        elif text.startswith("/admin_broadcast ") and self.is_admin(user_id):
            message = text[16:].strip()
            if message:
                return chat_id, f"📢 Broadcast sent: {message}"
            return chat_id, "❌ Usage: /admin_broadcast [message]"
        
        elif text.startswith("/admin") and not self.is_admin(user_id):
            return chat_id, "⛔ Admin only command!"
        
        # AI Chat
        elif not text.startswith("/"):
            return chat_id, "🤖 Processing..."
        
        return None, None
    
    def run(self):
        """Main polling loop for this bot"""
        from genesis_protocol.ai.provider_chain import get_provider_chain
        ai = get_provider_chain()
        
        print(f"[{self.username}] Starting polling...")
        self.running = True
        
        while self.running:
            try:
                resp = httpx.get(f"{self.api}/getUpdates", 
                               params={"offset": self.offset, "timeout": 30}, 
                               timeout=35).json()
                
                if not resp.get("ok"):
                    time.sleep(5)
                    continue
                
                updates = resp.get("result", [])
                if not updates:
                    continue
                
                for update in updates:
                    self.offset = update["update_id"] + 1
                    
                    if "message" not in update:
                        continue
                    
                    msg = update["message"]
                    print(f"[{self.username}] 📨 {msg.get('from', {}).get('first_name', 'User')}: {msg.get('text', '')[:50]}")
                    
                    chat_id, response = self.handle_message(msg)
                    
                    if response:
                        self.send(chat_id, response)
                        
                        # AI processing for /ask and regular messages
                        text = msg.get("text", "")
                        if text.startswith("/ask ") or (not text.startswith("/")):
                            question = text[5:] if text.startswith("/ask ") else text
                            try:
                                import asyncio
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                
                                result = loop.run_until_complete(
                                    ai.call(
                                        messages=[
                                            {"role": "system", "content": f"You are {self.username}. Keep responses helpful and concise."},
                                            {"role": "user", "content": question}
                                        ],
                                        user_input=question
                                    )
                                )
                                loop.close()
                                
                                if result.success and result.response:
                                    ai_response = result.response.content[:4000]
                                    self.send(chat_id, f"🤖 *Genesis AI:*\n\n{ai_response}")
                                else:
                                    self.send(chat_id, f"❌ Error: {result.error[:500] if result.error else 'Unknown'}")
                            except Exception as e:
                                self.send(chat_id, f"❌ Error: {str(e)[:500]}")
                
            except KeyboardInterrupt:
                print(f"[{self.username}] Stopping...")
                self.running = False
                break
            except Exception as e:
                print(f"[{self.username}] Error: {e}")
                time.sleep(5)


def main():
    config = get_config()
    
    print("=" * 60)
    print("🤖 GENESIS PROTOCOL - ALL TELEGRAM BOTS")
    print("=" * 60)
    print(f"Admins configured: {len(ADMIN_IDS)}")
    print()
    
    # Get all bots
    bots = []
    
    # Main bot
    if config.telegram.bot_token:
        bots.append(TelegramBot(
            config.telegram.bot_token,
            config.telegram.bot_username,
            ADMIN_IDS
        ))
        print(f"✅ Main bot: @{config.telegram.bot_username}")
    
    # Additional bots
    if config.telegram.additional_bot_tokens:
        tokens = [t.strip() for t in config.telegram.additional_bot_tokens.split(",") if t.strip()]
        bot_names = ["@Gen_sisbot", "@Genesis_makebot"]  # Map to names
        
        for i, token in enumerate(tokens[:2]):  # Max 2 additional bots
            username = bot_names[i] if i < len(bot_names) else f"bot_{i+2}"
            bots.append(TelegramBot(token, username, ADMIN_IDS))
            print(f"✅ Bot {i+2}: {username}")
    
    if not bots:
        print("❌ No bots configured!")
        print("Set TELEGRAM_BOT_TOKEN env var")
        return
    
    print()
    print(f"🚀 Starting {len(bots)} bot(s)...")
    print("=" * 60)
    
    # Start all bots in threads
    threads = []
    for bot in bots:
        t = threading.Thread(target=bot.run, daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.5)  # Stagger startup
    
    print("✅ All bots started!")
    print("Press Ctrl+C to stop")
    print()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping all bots...")
        for bot in bots:
            bot.running = False


if __name__ == "__main__":
    main()
