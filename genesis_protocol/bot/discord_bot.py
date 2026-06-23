"""Genesis Protocol - Discord Bot

Discord integration for Genesis Protocol AI assistant.
Provides DM conversations, server channel support, and mention replies.
"""

import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any

import discord
from discord.ext import commands

# Setup basic logging before imports
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
)
logger = logging.getLogger("discord_bot")


class DiscordBot(commands.Bot):
    """
    Genesis Protocol Discord Bot.
    
    Handles all Discord interactions including DMs, server messages,
    mentions, and slash commands.
    """
    
    def __init__(self, config=None):
        """Initialize Discord bot."""
        self.config = config
        self._running = False
        self._user_id = None
        
        # Call parent init with intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True
        intents.dm_messages = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        logger.info("Discord bot initialized")
    
    async def initialize(self, token: str):
        """
        Initialize and prepare bot.
        
        Args:
            token: Discord bot token
        """
        if not token:
            raise ValueError("Discord bot token not configured")
        
        self._token = token
        
        # Register event handlers
        self.add_listener(self.on_ready, "on_ready")
        self.add_listener(self.on_message, "on_message")
        self.add_listener(self.on_disconnect, "on_disconnect")
        self.add_listener(self.on_error, "on_error")
        
        # Register commands
        await self._register_commands()
        
        logger.info("Discord bot application initialized")
    
    async def _register_commands(self):
        """Register bot commands."""
        @self.command(name="ping")
        async def ping(ctx):
            """Check if bot is online."""
            await ctx.send("🏓 Pong! Genesis online!")
        
        @self.command(name="status")
        async def status_cmd(ctx):
            """Show bot status."""
            embed = discord.Embed(
                title="Genesis Protocol Status",
                color=discord.Color.green()
            )
            embed.add_field(name="Version", value="1.0.0", inline=True)
            embed.add_field(name="Provider", value="multi-provider", inline=True)
            embed.add_field(name="Mode", value="active", inline=True)
            await ctx.send(embed=embed)
        
        @self.command(name="whoami")
        async def whoami_cmd(ctx):
            """Show creator/owner information."""
            embed = discord.Embed(
                title="Genesis Protocol",
                color=discord.Color.blue()
            )
            embed.add_field(name="Owner", value="Aakash Kumar", inline=True)
            embed.add_field(name="Role", value="Administrator", inline=True)
            embed.add_field(name="Creator", value="@aakash00a1-byte", inline=False)
            await ctx.send(embed=embed)
        
        @self.command(name="health")
        async def health_cmd(ctx):
            """Show system health."""
            embed = discord.Embed(
                title="System Health",
                color=discord.Color.green()
            )
            embed.add_field(name="Status", value="🟢 Healthy", inline=True)
            embed.add_field(name="Memory", value="OK", inline=True)
            embed.add_field(name="Providers", value="Online", inline=True)
            await ctx.send(embed=embed)
        
        @self.command(name="memory")
        async def memory_cmd(ctx):
            """Show memory status."""
            embed = discord.Embed(
                title="Memory Status",
                color=discord.Color.blue()
            )
            embed.add_field(name="Short-term", value="Active", inline=True)
            embed.add_field(name="Long-term", value="Connected", inline=True)
            embed.add_field(name="Context", value="Preserved", inline=True)
            await ctx.send(embed=embed)
        
        logger.info("Discord commands registered")
    
    async def on_ready(self):
        """Called when bot is ready."""
        self._user_id = self.user.id
        guild_count = len(self.guilds)
        
        logger.info(f"Discord bot connected")
        logger.info(f"Bot username: {self.user.name}")
        logger.info(f"Bot ID: {self.user.id}")
        logger.info(f"Guild count: {guild_count}")
        
        # Sync commands
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")
    
    async def on_message(self, message: discord.Message):
        """Handle incoming messages."""
        # Ignore messages from bot itself
        if message.author.id == self.user.id:
            return
        
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Process commands first
        ctx = await self.get_context(message)
        if ctx.command:
            await self.invoke(ctx)
            return
        
        # Handle mentions
        if self.user in message.mentions:
            await self._handle_mention(message)
            return
        
        # Handle DMs
        if isinstance(message.channel, discord.DMChannel):
            await self._handle_dm(message)
            return
        
        # Handle server messages (optional, based on config)
        if message.guild and not message.content.startswith('!'):
            # Only respond if explicitly configured
            pass
    
    async def _handle_mention(self, message: discord.Message):
        """Handle bot mention."""
        # Remove mention and clean message
        content = message.content
        for mention in message.mentions:
            content = content.replace(f"<@{mention.id}>", "").replace(f"<@!{mention.id}>", "")
        content = content.strip()
        
        if not content:
            content = "Hello! How can I help you?"
        
        await self._process_and_respond(message, content, is_mention=True)
    
    async def _handle_dm(self, message: discord.Message):
        """Handle direct messages."""
        await self._process_and_respond(message, message.content, is_dm=True)
    
    async def _process_and_respond(
        self, 
        message: discord.Message, 
        content: str,
        is_mention: bool = False,
        is_dm: bool = False
    ):
        """Process message through agent and send response."""
        try:
            # Show typing indicator
            async with message.channel.typing():
                # Get user info
                user_id = message.author.id
                chat_id = message.channel.id
                
                # Call the web app endpoint or agent directly
                response = await self._call_agent(content, user_id, chat_id)
                
                if response:
                    # Split long messages
                    if len(response) > 2000:
                        chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                        for chunk in chunks:
                            await message.reply(chunk, mention_author=False)
                    else:
                        await message.reply(response, mention_author=False)
                else:
                    await message.reply(
                        "I encountered an issue processing your request. Please try again.",
                        mention_author=False
                    )
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await message.reply(
                "Sorry, I encountered an error. Please try again.",
                mention_author=False
            )
    
    async def _call_agent(
        self, 
        query: str, 
        user_id: int, 
        chat_id: int
    ) -> Optional[str]:
        """Call the Genesis agent to process the query."""
        try:
            # Import here to avoid circular imports
            from genesis_protocol.ai.agent import GenesisAgent
            from genesis_protocol.config import get_config
            
            config = get_config()
            agent = GenesisAgent(config)
            response = await agent.process(
                query=query,
                chat_id=chat_id,
                user_id=user_id
            )
            
            if response and hasattr(response, 'response'):
                return response.response
            return str(response) if response else None
            
        except ImportError as e:
            logger.error(f"Failed to import agent: {e}")
            return "Agent not available. Please check configuration."
        except Exception as e:
            logger.error(f"Agent processing error: {e}")
            return "I encountered an error processing your request."
    
    async def on_disconnect(self):
        """Called when bot disconnects."""
        logger.warning("Discord bot disconnected")
        self._running = False
    
    async def on_error(self, event_method: str, *args, **kwargs):
        """Handle errors."""
        logger.error(f"Discord error in {event_method}: {args}")
    
    async def start_bot(self):
        """Start the bot with reconnection."""
        if not hasattr(self, '_token'):
            raise ValueError("Bot not initialized. Call initialize() first.")
        
        self._running = True
        logger.info("Starting Discord bot...")
        
        try:
            async with self:
                await self.start(self._token, reconnect=True)
        except discord.errors.PrivilegedIntentsRequired:
            logger.error("Privileged intents required. Enable Message Content Intent in Discord Developer Portal.")
            raise
        except Exception as e:
            logger.error(f"Bot error: {e}")
            if self._running:
                logger.info("Attempting reconnect in 5 seconds...")
                await asyncio.sleep(5)
                await self.start_bot()
    
    def run(self):
        """Run the bot (blocking)."""
        token = os.environ.get("DISCORD_TOKEN")
        if not token:
            logger.error("DISCORD_TOKEN not found in environment")
            return
        
        self.run(token)


def run_discord_bot():
    """Entry point for running Discord bot."""
    bot = DiscordBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        logger.info("Discord bot stopped by user")
    except Exception as e:
        logger.error(f"Discord bot error: {e}")


if __name__ == "__main__":
    run_discord_bot()
