"""Genesis Protocol - Main Application Entry Point

Autonomous Multimodal AI Agent with Telegram Interface.
"""

import asyncio
import signal
from pathlib import Path

from genesis_protocol.config import get_config, Config
from genesis_protocol.utils.logger import setup_logging, get_logger
from genesis_protocol.bot.telegram_bot import TelegramBot

# Initialize logging
setup_logging()
logger = get_logger("main")


class GenesisProtocol:
    """
    Main Genesis Protocol application.
    
    Orchestrates all components and manages application lifecycle.
    """
    
    def __init__(self, config: Config = None):
        """Initialize application."""
        self.config = config or get_config()
        self.bot: TelegramBot = None
        self._running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing Genesis Protocol...")
        
        # Validate configuration
        warnings = self.config.validate()
        if warnings:
            for warning in warnings:
                logger.warning(f"Config warning: {warning}")
        
        # Initialize Telegram bot
        self.bot = TelegramBot(self.config)
        await self.bot.initialize()
        
        logger.info("Genesis Protocol initialized successfully")
    
    async def start(self):
        """Start the application."""
        if not self.bot:
            await self.initialize()
        
        self._running = True
        
        logger.info("Starting Genesis Protocol...")
        
        try:
            # Start Telegram bot
            await self.bot.start()
            
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
    
    async def stop(self):
        """Stop the application."""
        logger.info("Stopping Genesis Protocol...")
        
        self._running = False
        
        if self.bot:
            await self.bot.stop()
        
        logger.info("Genesis Protocol stopped")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(self.stop())


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    
    # Create and run application
    app = GenesisProtocol()
    
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())