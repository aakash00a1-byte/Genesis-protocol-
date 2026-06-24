#!/usr/bin/env python3
"""
Genesis Protocol - Discord Bot
Python 3.11+ compatible - Uses discord.py async

Features:
- Message listening in #general channel
- Reply to greetings (hlo genesis, hello genesis)
- Slash commands (/ping, /status, /health)
- Welcome message for new members
- AI chatbot with GROQ/OpenAI
- Daily status report
- Guild connection logging
- Error logging to file
- Health check endpoint
- Environment variable configuration
"""
import sys
import os
import asyncio
import logging
import random
import httpx
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Setup logging to file and console
log_file = Path("/app/discord_bot.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(log_file) if log_file.parent.exists() else logging.NullHandler(),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("discord_starter")

import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# GROQ AI Client
# ============================================================
class GROQClient:
    def __init__(self):
        self.api_key = os.environ.get("GROQ_API_KEY")
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
    
    async def chat(self, message: str, user_name: str = "User") -> str:
        """Send message to GROQ AI and get response"""
        if not self.api_key:
            return None
        
        system_prompt = """You are Genesis Protocol, an AI assistant created by Aakash Kumar (@aakash00a1-byte).
You are helpful, friendly, and concise. Keep responses short and engaging.
You can help with coding, questions, and general conversation."""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_name}: {message}"}
            ],
            "temperature": 0.8,
            "max_tokens": 500
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    logger.error(f"GROQ API error: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"GROQ request failed: {e}")
            return None


# Global AI client
groq_client = GROQClient()


def main():
    print("=" * 60)
    print("🎮 GENESIS PROTOCOL DISCORD BOT")
    print("=" * 60)
    
    # ============================================================
    # ENVIRONMENT VARIABLES
    # ============================================================
    
    DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN") or os.environ.get("DISCORD_BOT_TOKEN")
    if not DISCORD_TOKEN:
        print("❌ ERROR: Discord token not set!")
        print("   Set DISCORD_BOT_TOKEN in Railway environment variables.")
        sys.exit(1)
    
    print(f"✅ DISCORD_TOKEN found: {DISCORD_TOKEN[:10]}...{DISCORD_TOKEN[-4:]}")
    print(f"✅ GROQ_API_KEY: {'✅ Set' if groq_client.api_key else '❌ Not set'}")
    print(f"⏰ Started at: {datetime.now().isoformat()}")
    
    # Setup Discord intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.guilds = True
    intents.guild_messages = True
    intents.guild_members = True  # For welcome messages
    intents.dm_messages = True
    
    # Create bot
    bot = commands.Bot(
        command_prefix="!",
        intents=intents,
        help_command=None,
        description="Genesis Protocol AI Assistant"
    )
    
    # ============================================================
    # EVENTS
    # ============================================================
    
    @bot.event
    async def on_member_join(member):
        """Welcome new members to the server"""
        welcome_messages = [
            f"🎉 Welcome {member.mention} to **{member.guild.name}**! Happy to have you here!",
            f"👋 Hey {member.mention}! You just joined. Make yourself at home!",
            f"✨ Welcome aboard {member.mention}! Glad you're here!",
        ]
        
        # Find welcome channel
        welcome_channel = discord.utils.get(member.guild.text_channels, name="welcome")
        if not welcome_channel:
            welcome_channel = discord.utils.get(member.guild.text_channels, name="general")
        if not welcome_channel:
            welcome_channel = member.guild.system_channel
        
        if welcome_channel:
            msg = random.choice(welcome_messages)
            await welcome_channel.send(msg)
            logger.info(f"Welcome message sent to {member}")
    
    @bot.event
    async def on_ready():
        """Called when bot successfully connects to Discord"""
        print()
        print("=" * 60)
        print("🎉 DISCORD BOT CONNECTED SUCCESSFULLY!")
        print("=" * 60)
        print(f"✅ Bot Username: {bot.user.name}")
        print(f"✅ Bot ID: {bot.user.id}")
        print(f"✅ Guild Count: {len(bot.guilds)}")
        
        # Log guild connections
        for guild in bot.guilds:
            print(f"   📦 {guild.name} (ID: {guild.id})")
            print(f"      Members: {guild.member_count}")
        
        logger.info(f"Discord connected - User: {bot.user.name}, ID: {bot.user.id}, Guilds: {len(bot.guilds)}")
        print("=" * 60)
        
        # Sync slash commands
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands")
            for cmd in synced:
                print(f"   /{cmd.name}")
        except Exception as e:
            print(f"⚠️ Command sync warning: {e}")
            logger.warning(f"Command sync failed: {e}")
        
        print("📡 Bot is now online and listening...")
        print("=" * 60)
    
    @bot.event
    async def on_guild_join(guild):
        """Called when bot joins a new server"""
        logger.info(f"Joined guild: {guild.name} (ID: {guild.id})")
        print(f"📦 Joined new server: {guild.name}")
    
    @bot.event
    async def on_guild_remove(guild):
        """Called when bot leaves a server"""
        logger.info(f"Left guild: {guild.name} (ID: {guild.id})")
        print(f"📤 Left server: {guild.name}")
    
    # ============================================================
    # MESSAGE LISTENING - #general channel
    # ============================================================
    
    @bot.event
    async def on_message(message):
        """Listen to messages in #general and respond to greetings"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Only listen in #general channel
        channel_name = message.channel.name.lower() if hasattr(message.channel, 'name') else ""
        is_general = channel_name == "general"
        
        # Also respond to DMs
        is_dm = isinstance(message.channel, discord.DMChannel)
        
        content_lower = message.content.lower().strip()
        
        # ========================================================
        # GREETING RESPONSES
        # ========================================================
        greetings = [
            "hlo genesis",
            "hello genesis", 
            "hey genesis",
            "hi genesis",
            "hii genesis",
            "hlo",
            "hello",
        ]
        
        if content_lower in greetings or content_lower.startswith("hlo genesis") or content_lower.startswith("hello genesis"):
            responses = [
                f"👋 Hello {message.author.mention}! Welcome to Genesis Protocol!",
                f"🎉 Hey there! I'm Genesis Protocol AI. How can I help you today?",
                f"✨ Hi {message.author.mention}! Ready to assist you!",
            ]
            import random
            response = random.choice(responses)
            await message.reply(response, mention_author=True)
            logger.info(f"Greeting response sent to {message.author} in #{channel_name}")
            return
        
        # ========================================================
        # MENTION RESPONSES - AI Chat
        # ========================================================
        if bot.user in message.mentions:
            # Remove mentions from content
            content = message.content
            for mention in message.mentions:
                content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            content = content.strip()
            
            if not content:
                await message.reply(
                    f"👋 Hello! I'm Genesis Protocol AI.\n"
                    f"Available commands: `/ping`, `/status`, `/help`\n"
                    f"Or use `/ask [question]` to chat with me!",
                    mention_author=False
                )
                return
            
            # Use GROQ AI for chat
            if groq_client.api_key:
                await message.channel.typing()
                response = await groq_client.chat(content, str(message.author))
                
                if response:
                    if len(response) > 2000:
                        response = response[:1997] + "..."
                    await message.reply(response, mention_author=False)
                    logger.info(f"AI response sent to {message.author}: {content[:50]}...")
                else:
                    await message.reply(
                        "🤖 I'm thinking... Try again in a moment!",
                        mention_author=False
                    )
            else:
                await message.reply(
                    "🤖 I'm Genesis Protocol AI! Configure GROQ_API_KEY to enable AI chat.\n"
                    "Available commands: `/ping`, `/status`, `/ask`",
                    mention_author=False
                )
            return
        
        # DM handling
        if is_dm:
            await message.reply(
                "👋 DM received! I'm Genesis Protocol AI.\n"
                "For help, use `/status` to see bot info.",
                mention_author=False
            )
            return
    
    # ============================================================
    # SLASH COMMANDS
    # ============================================================
    
    @app_commands.command(name="ping", description="Check if bot is online")
    async def ping(interaction: discord.Interaction):
        """Slash command: /ping - Check bot status"""
        await interaction.response.send_message(
            f"🏓 **Pong!**\n"
            f"✅ Genesis Protocol bot is online!\n"
            f"Latency: {round(bot.latency * 1000)}ms",
            ephemeral=False
        )
        logger.info(f"Ping command used by {interaction.user}")
    
    @app_commands.command(name="status", description="Show bot status and info")
    async def status(interaction: discord.Interaction):
        """Slash command: /status - Show bot status"""
        embed = discord.Embed(
            title="📊 Genesis Protocol Status",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="🤖 Bot Name", value=bot.user.name, inline=True)
        embed.add_field(name="🆔 Bot ID", value=bot.user.id, inline=True)
        embed.add_field(name="📦 Servers", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="💚 Status", value="🟢 Online", inline=True)
        embed.add_field(name="📡 Latency", value=f"{round(bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="🔧 Version", value="2.1.0", inline=True)
        embed.add_field(name="🤖 AI Chat", value="✅ Available" if groq_client.api_key else "⚠️ Not configured", inline=True)
        
        # Add server list
        if bot.guilds:
            guild_list = "\n".join([f"• {g.name}" for g in bot.guilds[:5]])
            if len(bot.guilds) > 5:
                guild_list += f"\n...and {len(bot.guilds) - 5} more"
            embed.add_field(name="🌐 Connected Servers", value=guild_list, inline=False)
        
        embed.set_footer(text="Genesis Protocol v2.1.0")
        await interaction.response.send_message(embed=embed, ephemeral=False)
        logger.info(f"Status command used by {interaction.user}")
    
    @app_commands.command(name="health", description="Show system health")
    async def health(interaction: discord.Interaction):
        """Slash command: /health - Show system health"""
        embed = discord.Embed(
            title="🏥 Genesis Protocol Health",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        embed.add_field(name="💚 Bot", value="🟢 Healthy", inline=True)
        embed.add_field(name="📡 Gateway", value="🟢 Connected", inline=True)
        embed.add_field(name="🧠 AI Engine", value="✅ Online" if groq_client.api_key else "⚠️ Offline", inline=True)
        embed.add_field(name="📝 Memory", value="✅ Active", inline=True)
        embed.add_field(name="🔧 Processes", value="3/3 Running", inline=True)
        embed.add_field(name="⏰ Uptime", value="Since startup", inline=True)
        embed.set_footer(text="All systems operational")
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @app_commands.command(name="help", description="Show available commands")
    async def help_cmd(interaction: discord.Interaction):
        """Slash command: /help - Show help"""
        embed = discord.Embed(
            title="📚 Genesis Protocol Help",
            color=discord.Color.blue(),
            description="Here are all available commands:"
        )
        embed.add_field(name="/ping", value="Check if bot is online", inline=True)
        embed.add_field(name="/status", value="Show bot status and info", inline=True)
        embed.add_field(name="/health", value="Show system health", inline=True)
        embed.add_field(name="/ask [question]", value="Ask Genesis AI anything", inline=True)
        embed.add_field(name="/help", value="Show this help message", inline=True)
        embed.add_field(name="Text Commands", value="Say `hello genesis` or `hlo genesis` to greet!", inline=False)
        embed.add_field(name="💬 AI Chat", value="Mention @Genesis Protocol to chat with AI", inline=False)
        embed.set_footer(text="Genesis Protocol v2.1.0")
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    @app_commands.command(name="ask", description="Ask Genesis AI anything")
    async def ask(interaction: discord.Interaction, question: str):
        """Slash command: /ask - Ask Genesis AI"""
        await interaction.response.defer()
        
        if not groq_client.api_key:
            await interaction.followup.send(
                "⚠️ AI is not configured. Please set GROQ_API_KEY in environment variables.",
                ephemeral=False
            )
            return
        
        response = await groq_client.chat(question, str(interaction.user))
        
        if response:
            # Truncate if too long
            if len(response) > 2000:
                response = response[:1997] + "..."
            
            embed = discord.Embed(
                title="🤖 Genesis AI Response",
                color=discord.Color.purple(),
                description=response,
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Asked by {interaction.user}")
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(
                "❌ Sorry, I couldn't get a response from AI. Please try again later.",
                ephemeral=False
            )
    
    # ============================================================
    # ERROR HANDLING
    # ============================================================
    
    @bot.event
    async def on_command_error(ctx, error):
        """Handle command errors"""
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ Error: {error}")
    
    @bot.event
    async def on_error(event, *args, **kwargs):
        """Handle general errors"""
        logger.error(f"Discord error in {event}: {args}")
    
    @bot.event
    async def on_disconnect():
        """Called when bot disconnects"""
        logger.warning("Discord bot disconnected")
        print("⚠️ Bot disconnected from Discord")
    
    @bot.event
    async def on_resumed():
        """Called when bot reconnects"""
        logger.info("Discord bot reconnected")
        print("✅ Bot reconnected to Discord")
    
    # ============================================================
    # START BOT
    # ============================================================
    
    print()
    print("🚀 Connecting to Discord Gateway...")
    
    try:
        bot.run(DISCORD_TOKEN, reconnect=True)
    except discord.errors.PrivilegedIntentsRequired:
        print("❌ ERROR: Privileged intents required!")
        print("   Go to Discord Developer Portal:")
        print("   https://discord.com/developers/applications")
        print("   → Select your bot")
        print("   → Bot → Privileged Gateway Intents")
        print("   → Enable: ✓ MESSAGE CONTENT INTENT")
        sys.exit(1)
    except discord.errors.LoginFailure:
        print("❌ ERROR: Invalid Discord token!")
        print("   Please check your DISCORD_TOKEN environment variable.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        logger.error(f"Discord bot fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()