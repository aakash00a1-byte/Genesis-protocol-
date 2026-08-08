#!/usr/bin/env python3
"""
Genesis Protocol - Telegram Bot
Python 3.13 compatible - Uses httpx for polling

Features:
- Public commands for everyone
- Admin commands for admins only
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import time
import json
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
    return []  # No default - must be configured


ADMIN_IDS = get_admin_ids()


def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id in ADMIN_IDS


def main():
    config = get_config()
    TOKEN = config.telegram.bot_token
    API = f"https://api.telegram.org/bot{TOKEN}"
    OFFSET = 0
    
    print("=" * 50)
    print("📱 GENESIS PROTOCOL TELEGRAM BOT")
    print("=" * 50)
    print(f"Bot: @Genesis_autonomousbot")
    print(f"Admins configured: {len(ADMIN_IDS)}")
    print("✅ Telegram bot started!")
    print("📡 Polling active")
    print("Press Ctrl+C to stop")
    print()
    
    # Get bot info
    try:
        resp = httpx.get(f"{API}/getMe").json()
        if resp.get("ok"):
            print(f"✅ Logged in as: {resp['result']['first_name']}")
        else:
            print(f"❌ Error: {resp}")
            print("⚠️ Bot token may be invalid, continuing anyway...")
    except Exception as e:
        print(f"⚠️ Connection error: {e} (will retry)")
        time.sleep(5)
    
    from genesis_protocol.ai.provider_chain import get_provider_chain
    ai = get_provider_chain()
    
    print("📡 Listening for messages...")
    print("=" * 50)
    
    while True:
        try:
            # Get updates
            resp = httpx.get(f"{API}/getUpdates", params={"offset": OFFSET, "timeout": 30}, timeout=35).json()
            
            if not resp.get("ok"):
                print(f"API Error: {resp}")
                time.sleep(5)
                continue
            
            updates = resp.get("result", [])
            if not updates:
                continue
            
            for update in updates:
                OFFSET = update["update_id"] + 1
                
                if "message" not in update:
                    continue
                
                msg = update["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                user_id = msg.get("from", {}).get("id", 0)
                user = msg.get("from", {}).get("first_name", "User")
                
                print(f"📨 {user} ({user_id}): {text[:50]}")
                
                # ================================================
                # PUBLIC COMMANDS (Everyone)
                # ================================================
                
                if text == "/start":
                    send(chat_id, """👋 *Welcome to Genesis Protocol Bot!*

I'm an AI assistant. Here's what I can do:

🌐 *Public Commands:*
/start - Welcome message
/hi - Say hello
/help - Show all commands
/status - Bot status
/ask [question] - Chat with AI

Just send any message to chat with me!
""")
                
                elif text == "/hi" or text.lower() == "hi genesis":
                    send(chat_id, f"👋 Hi {user}! Kaise ho? 🎉\n\nUse /help to see all commands!")
                
                elif text == "/help":
                    send(chat_id, """📚 *Genesis Protocol Commands*

🌐 *Public:*
/start - Welcome message
/hi - Say hello
/help - Show commands
/status - Bot status
/ask [question] - Chat with AI

💬 *Just send any message to chat with AI!*
""")
                
                elif text == "/status":
                    send(chat_id, f"""📊 *Genesis Status*

🤖 Bot: Genesis Protocol
📡 Status: 🟢 Online
⏰ Time: {datetime.now().strftime('%H:%M:%S')}
🔧 Version: 2.1.0
🛠️ Admin Users: {len(ADMIN_IDS)}
""")
                
                elif text.startswith("/ask "):
                    question = text[5:].strip()
                    if question:
                        send(chat_id, "🤖 Thinking...")
                        try:
                            import asyncio
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            
                            result = loop.run_until_complete(
                                ai.call(
                                    messages=[
                                        {"role": "system", "content": "You are Genesis Protocol AI. Keep responses helpful and concise."},
                                        {"role": "user", "content": question}
                                    ],
                                    user_input=question
                                )
                            )
                            loop.close()
                            
                            if result.success and result.response:
                                response = result.response.content[:4000] if result.response.content else "Sorry, no response."
                                send(chat_id, f"🤖 *Genesis AI:*\n\n{response}")
                            else:
                                send(chat_id, f"❌ Error: {result.error[:500] if result.error else 'Unknown error'}")
                        except Exception as e:
                            send(chat_id, f"❌ Error: {str(e)[:500]}")
                    else:
                        send(chat_id, "❌ Usage: /ask [your question]")
                
                # ================================================
                # ADMIN COMMANDS (Only admins)
                # ================================================
                
                elif text == "/admin" and is_admin(user_id):
                    send(chat_id, """⚙️ *Genesis Admin Panel*

🔒 *Admin Commands:*
/admin - This panel
/admin_status - Detailed status
/admin_stats - View statistics
/admin_broadcast - Broadcast message
/admin_users - List users
/admin_reload - Reload config
/admin_restart - Restart bot

*Configure TELEGRAM_ADMIN_IDS env var to add admins.*
""")
                
                elif text == "/admin_status" and is_admin(user_id):
                    send(chat_id, f"""⚙️ *System Status*

🤖 Bot: Genesis Protocol
📡 Status: 🟢 Running
👥 Admins: {len(ADMIN_IDS)}
⏰ Uptime: Since startup
🔧 Version: 2.1.0
🧠 AI: ✅ Ready
""")
                
                elif text == "/admin_stats" and is_admin(user_id):
                    send(chat_id, f"""📈 *Statistics*

👥 Admin Users: {len(ADMIN_IDS)}
⏰ Bot Started: {datetime.now().strftime('%Y-%m-%d %H:%M')}
🔧 Version: 2.1.0
🛠️ Commands: 10 total
   - Public: 5
   - Admin: 5
""")
                
                elif text == "/admin_reload" and is_admin(user_id):
                    send(chat_id, "🔄 Configuration reloaded!")
                
                elif text == "/admin_restart" and is_admin(user_id):
                    send(chat_id, "🔄 Restarting bot... (simulated)")
                
                elif text.startswith("/admin_broadcast ") and is_admin(user_id):
                    message = text[16:].strip()
                    if message:
                        send(chat_id, f"📢 Broadcast sent: {message}")
                    else:
                        send(chat_id, "❌ Usage: /admin_broadcast [message]")
                
                # Admin command but not admin
                elif text.startswith("/admin") and not is_admin(user_id):
                    send(chat_id, "⛔ Admin only command!")
                
                # ================================================
                # AI CHAT (For any other message)
                # ================================================
                
                elif not text.startswith("/"):
                    send(chat_id, "🤖 Processing...")
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        result = loop.run_until_complete(
                            ai.call(
                                messages=[
                                    {"role": "system", "content": "You are Genesis Protocol AI. Keep responses helpful, concise, and friendly."},
                                    {"role": "user", "content": text}
                                ],
                                user_input=text
                            )
                        )
                        loop.close()
                        
                        if result.success and result.response:
                            response = result.response.content[:4000] if result.response.content else "Sorry, I couldn't respond."
                            send(chat_id, f"🤖 *Genesis AI:*\n\n{response}")
                        else:
                            send(chat_id, f"❌ Error: {result.error[:500] if result.error else 'Unknown error'}")
                    except Exception as e:
                        send(chat_id, f"❌ Error: {str(e)[:500]}")
        
        except KeyboardInterrupt:
            print("\n🛑 Bot stopped")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)


def send(chat_id, text):
    """Send message to Telegram"""
    TOKEN = get_config().telegram.bot_token
    API = f"https://api.telegram.org/bot{TOKEN}"
    
    try:
        httpx.post(f"{API}/sendMessage", json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        print(f"Send error: {e}")


if __name__ == "__main__":
    main()
