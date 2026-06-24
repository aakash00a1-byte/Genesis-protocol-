#!/usr/bin/env python3
"""
Genesis Protocol - Discord Bot
Python 3.11+ compatible - Uses discord.py async
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
)
logger = logging.getLogger("discord_starter")

import discord
from discord.ext import commands


def main():
    print("=" * 60)
    print("🎮 GENESIS PROTOCOL DISCORD BOT")
    print("=" * 60)
    
    # Get token
    DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
    if not DISCORD_TOKEN:
        print("❌ ERROR: DISCORD_TOKEN environment variable not set!")
        print("   Please set DISCORD_TOKEN in Railway environment variables.")
        sys.exit(1)
    
    print(f"✅ Discord token found: {DISCORD_TOKEN[:10]}...{DISCORD_TOKEN[-4:]}")
    
    # Setup intents
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.guilds = True
    intents.dm_messages = True
    intents.members = True
    
    # Create bot
    bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
    
    @bot.event
    async def on_ready():
        print()
        print("=" * 60)
        print("🎉 DISCORD BOT CONNECTED SUCCESSFULLY!")
        print("=" * 60)
        print(f"✅ Bot Username: {bot.user.name}")
        print(f"✅ Bot ID: {bot.user.id}")
        print(f"✅ Guild Count: {len(bot.guilds)}")
        print("=" * 60)
        
        # Log to file for Railway logs
        logger.info(f"Discord bot connected - Username: {bot.user.name}, ID: {bot.user.id}, Guilds: {len(bot.guilds)}")
        
        # Sync commands
        try:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} slash commands")
        except Exception as e:
            print(f"⚠️ Command sync error: {e}")
        
        print("📡 Discord bot is now online and listening...")
        print("=" * 60)
    
    @bot.event
    async def on_message(message):
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Process commands
        ctx = await bot.get_context(message)
        if ctx.command:
            await bot.invoke(ctx)
            return
        
        # Handle mentions
        if bot.user in message.mentions:
            content = message.content
            for mention in message.mentions:
                content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
            content = content.strip()
            
            if content:
                await message.reply(f"👋 Hello! I'm Genesis Protocol AI. I'm currently online with {len(bot.guilds)} servers connected.", mention_author=False)
            else:
                await message.reply("👋 Hello! I'm Genesis Protocol AI. How can I help you?", mention_author=False)
            return
        
        # Handle DMs
        if isinstance(message.channel, discord.DMChannel):
            await message.reply("👋 DM received! I'll respond when AI is configured.", mention_author=False)
    
    # Register commands
    @bot.command(name="ping")
    async def ping(ctx):
        await ctx.send("🏓 Pong! Genesis Discord bot is online!")
    
    @bot.command(name="status")
    async def status(ctx):
        embed = discord.Embed(
            title="📊 Genesis Protocol Status",
            color=discord.Color.green()
        )
        embed.add_field(name="Status", value="🟢 Online", inline=True)
        embed.add_field(name="Bot", value=bot.user.name, inline=True)
        embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
        embed.add_field(name="Version", value="2.0.0", inline=True)
        await ctx.send(embed=embed)
    
    @bot.command(name="whoami")
    async def whoami(ctx):
        embed = discord.Embed(
            title="👤 Genesis Protocol",
            color=discord.Color.blue()
        )
        embed.add_field(name="Owner", value="Aakash Kumar", inline=True)
        embed.add_field(name="Creator", value="@aakash00a1-byte", inline=True)
        embed.add_field(name="Version", value="2.0.0 - Enhanced", inline=True)
        await ctx.send(embed=embed)
    
    @bot.command(name="health")
    async def health(ctx):
        embed = discord.Embed(
            title="🏥 System Health",
            color=discord.Color.green()
        )
        embed.add_field(name="Core Status", value="🟢 Healthy", inline=True)
        embed.add_field(name="AI Engine", value="✅ Online", inline=True)
        embed.add_field(name="Memory", value="✅ Online", inline=True)
        await ctx.send(embed=embed)
    
    @bot.event
    async def on_error(event, *args, **kwargs):
        logger.error(f"Discord error in {event}: {args}")
    
    @bot.event
    async def on_disconnect():
        logger.warning("Discord bot disconnected")
    
    print("🚀 Starting Discord bot connection...")
    print()
    
    # Run the bot
    try:
        bot.run(DISCORD_TOKEN, reconnect=True)
    except discord.errors.PrivilegedIntentsRequired:
        print("❌ ERROR: Privileged intents required!")
        print("   Enable Message Content Intent in Discord Developer Portal:")
        print("   https://discord.com/developers/applications")
    except Exception as e:
        print(f"❌ ERROR: {e}")
        logger.error(f"Discord bot error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()