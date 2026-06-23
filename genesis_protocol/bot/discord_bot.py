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
            from genesis_protocol.ai.enhancements import emotional
            response = emotional.get_emotional_response({}, 1.0)
            await ctx.send(f"🏓 Pong! {response} Genesis online!")
        
        @self.command(name="status")
        async def status_cmd(ctx):
            """Show bot status."""
            from genesis_protocol.ai.enhancements import multilingual, Language
            lang = multilingual.detect_language(ctx.message.content)
            
            embed = discord.Embed(
                title="📊 Genesis Protocol Status",
                color=discord.Color.green()
            )
            embed.add_field(name="Version", value="2.0.0", inline=True)
            embed.add_field(name="Provider", value="Multi-Provider AI", inline=True)
            embed.add_field(name="Mode", value="🟢 Active", inline=True)
            embed.add_field(name="Language", value=lang.value.upper(), inline=True)
            embed.add_field(name="NLP", value="✅ Enhanced", inline=True)
            embed.add_field(name="Emotional AI", value="✅ Active", inline=True)
            await ctx.send(embed=embed)
        
        @self.command(name="whoami")
        async def whoami_cmd(ctx):
            """Show creator/owner information."""
            embed = discord.Embed(
                title="👤 Genesis Protocol",
                color=discord.Color.blue()
            )
            embed.add_field(name="Owner", value="Aakash Kumar", inline=True)
            embed.add_field(name="Role", value="Administrator", inline=True)
            embed.add_field(name="Creator", value="@aakash00a1-byte", inline=False)
            embed.add_field(name="Version", value="2.0.0 - Enhanced", inline=True)
            await ctx.send(embed=embed)
        
        @self.command(name="health")
        async def health_cmd(ctx):
            """Show system health."""
            from genesis_protocol.ai.enhancements import learner
            embed = discord.Embed(
                title="🏥 System Health",
                color=discord.Color.green()
            )
            embed.add_field(name="Core Status", value="🟢 Healthy", inline=True)
            embed.add_field(name="NLP Engine", value="✅ Online", inline=True)
            embed.add_field(name="Emotional AI", value="✅ Online", inline=True)
            embed.add_field(name="Multilingual", value="✅ Online", inline=True)
            embed.add_field(name="Memory System", value="✅ Online", inline=True)
            embed.add_field(name="Security", value="✅ Active", inline=True)
            await ctx.send(embed=embed)
        
        @self.command(name="memory")
        async def memory_cmd(ctx):
            """Show memory status."""
            from genesis_protocol.ai.enhancements import learner, AutomatedLearner
            user_id = ctx.author.id
            knowledge = learner.get_knowledge(user_id)
            
            embed = discord.Embed(
                title="🧠 Memory Status",
                color=discord.Color.blue()
            )
            embed.add_field(name="Short-term", value="✅ Active", inline=True)
            embed.add_field(name="Long-term", value="✅ Connected", inline=True)
            embed.add_field(name="Context", value="✅ Preserved", inline=True)
            embed.add_field(name="Auto-Learning", value="✅ Enabled", inline=True)
            embed.add_field(name="Learned Facts", value=str(len(learner.learned_facts.get(user_id, []))), inline=True)
            
            if knowledge:
                embed.add_field(name="Your Info", value=knowledge[:100], inline=False)
            
            await ctx.send(embed=embed)
        
        @self.command(name="chart")
        async def chart_cmd(ctx):
            """Show data chart."""
            from genesis_protocol.ai.enhancements import DataVisualizer
            viz = DataVisualizer()
            data = {
                "NLP": 95,
                "Emotion": 88,
                "Multi-lang": 85,
                "Security": 92,
                "Learning": 78
            }
            chart = viz.create_chart(data, "bar")
            await ctx.send(f"```\n{chart}\n```")
        
        @self.command(name="privacy")
        async def privacy_cmd(ctx):
            """Show privacy tip."""
            from genesis_protocol.ai.enhancements import SecurityFeatures
            tip = SecurityFeatures.get_privacy_tip()
            await ctx.send(tip)
        
        @self.command(name="lang")
        async def lang_cmd(ctx):
            """Show supported languages."""
            from genesis_protocol.ai.enhancements import multilingual, Language
            lang = multilingual.detect_language(ctx.message.content)
            
            supported = "English 🇺🇸, Hindi 🇮🇳, Spanish 🇪🇸, French 🇫🇷, German 🇩🇪, Chinese 🇨🇳, Japanese 🇯🇵"
            await ctx.send(f"🌐 Supported Languages:\n{supported}\n\nDetected: {lang.value.upper()}")
        
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
                
                # Analyze message for emotions, intent, language
                from genesis_protocol.ai.enhancements import analyze_message, multilingual, emotional
                analysis = analyze_message(content)
                
                # Log analysis
                logger.info(f"User {user_id}: lang={analysis.language.value}, emotion={list(analysis.emotions.keys())[0].name if analysis.emotions else 'neutral'}, intent={analysis.intent}")
                
                # Check for data visualization request
                if 'chart' in content.lower() or 'data' in content.lower():
                    response = await self._handle_data_request(content, user_id)
                else:
                    # Call the agent
                    response = await self._call_agent(content, user_id, chat_id)
                
                # Add emotional prefix if response is empty
                if not response:
                    response = "I'm not sure how to help with that. Could you rephrase?"
                
                # Learn from interaction
                from genesis_protocol.ai.enhancements import learner
                learner.learn_from_interaction(user_id, content, str(response))
                
                if len(response) > 2000:
                    chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for chunk in chunks:
                        await message.reply(chunk, mention_author=False)
                else:
                    await message.reply(response, mention_author=False)
                        
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await message.reply(
                "Sorry, I encountered an error. Please try again.",
                mention_author=False
            )
    
    async def _handle_data_request(self, content: str, user_id: int) -> str:
        """Handle data visualization requests."""
        from genesis_protocol.ai.enhancements import DataVisualizer
        
        viz = DataVisualizer()
        
        # Example data based on request
        sample_data = {
            "OpenAI": 45.2,
            "Claude": 32.1,
            "Gemini": 28.7,
            "Llama": 18.5,
            "Mistral": 15.3
        }
        
        chart_type = "bar" if "bar" in content.lower() else "pie" if "pie" in content.lower() else "bar"
        return viz.create_chart(sample_data, chart_type)
    
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
    
    def run(self, token: str = None):
        """Run the bot (blocking)."""
        if token is None:
            token = os.environ.get("DISCORD_TOKEN")
        if not token:
            logger.error("DISCORD_TOKEN not found in environment")
            return
        
        super().run(token)


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
