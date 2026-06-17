#!/usr/bin/env python3
"""
Genesis Protocol - Telegram Bot
Python 3.13 compatible - Uses httpx for polling
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import time
import json
import httpx
from genesis_protocol.config import get_config

def main():
    config = get_config()
    TOKEN = config.telegram.bot_token
    API = f"https://api.telegram.org/bot{TOKEN}"
    OFFSET = 0
    
    print("=" * 50)
    print("📱 GENESIS PROTOCOL TELEGRAM BOT")
    print("=" * 50)
    print(f"Bot: @Genesis_autonomousbot")
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
            return
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return
    
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
                user = msg.get("from", {}).get("first_name", "User")
                
                print(f"📨 {user}: {text[:50]}")
                
                # Handle commands
                if text == "/start":
                    send(chat_id, f"👋 Hi {user}! I'm Genesis Protocol Bot. Send me any message!")
                elif text == "/hi":
                    send(chat_id, f"👋 Hi {user}! Kaise ho? 🎉")
                elif text == "/help":
                    send(chat_id, "Commands:\n/start - Start\n/hi - Hello\n/help - Help\n\nOr just send any message!")
                else:
                    send(chat_id, "🤖 Processing your message...")
                    
                    # Get AI response
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        result = loop.run_until_complete(
                            ai.call(
                                messages=[
                                    {"role": "system", "content": "You are a helpful AI assistant. Keep responses concise."},
                                    {"role": "user", "content": text}
                                ],
                                user_input=text
                            )
                        )
                        loop.close()
                        
                        if result.success:
                            response = result.response.content[:4000]
                            send(chat_id, f"🤖 Response:\n\n{response}")
                        else:
                            send(chat_id, f"❌ Error: {result.error[:500]}")
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
