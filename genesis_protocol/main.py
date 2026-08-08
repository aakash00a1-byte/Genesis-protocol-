"""Genesis Protocol - Main Application Entry Point

Channel Isolation Mode:
- Web Platform = Primary user interface
- Telegram = Admin monitoring interface
- Strict channel separation enforced
"""

import asyncio
import signal
import logging
import os
import sys
from pathlib import Path

# Add parent directory for web imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis_protocol.config import get_config, Config
from genesis_protocol.utils.logger import setup_logging, get_logger
from genesis_protocol.core.channel import Channel, get_channel_isolation
from genesis_protocol.core.admin_alerts import get_admin_alerts

# Initialize logging
setup_logging()
logger = get_logger("main")

# Get configuration
config = get_config()


class GenesisProtocol:
    """
    Main Genesis Protocol application with channel isolation.
    
    - Web Platform: Primary user interface
    - Telegram: Admin monitoring (optional)
    - Strict channel separation
    """
    
    def __init__(self, config: Config = None):
        """Initialize application."""
        self.config = config or get_config()
        self._running = False
        self.channel_isolation = get_channel_isolation()
        self.admin_alerts = get_admin_alerts()
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("=" * 50)
        logger.info("Genesis Protocol v2.0 - Channel Isolation Mode")
        logger.info("=" * 50)
        
        # Log channel configuration
        logger.info(f"TELEGRAM_ENABLED: {self.config.telegram_enabled}")
        logger.info(f"TELEGRAM_ADMIN_ONLY: {self.config.telegram_admin_only}")
        logger.info(f"Web Platform: PRIMARY")
        
        # Initialize admin alerts
        if self.config.telegram_admin_chat_id:
            self.admin_alerts.set_admin_chat_id(self.config.telegram_admin_chat_id)
            self.admin_alerts.enable()
            logger.info(f"Admin alerts enabled for chat ID: {self.config.telegram_admin_chat_id}")
        
        # Log startup
        self.channel_isolation.log_channel_activity(Channel.WEB, "startup", "Genesis Protocol started")
        
        logger.info("Genesis Protocol initialized successfully")
    
    async def start(self):
        """Start the application."""
        self._running = True
        
        logger.info("Starting Genesis Protocol...")
        
        try:
            # Start web platform (always)
            await self._start_web()
            
            # Start Telegram bot (if enabled)
            if self.config.telegram_enabled:
                await self._start_telegram()
        
        except Exception as e:
            logger.error(f"Application error: {e}")
            self.admin_alerts.alert_critical_error(str(e))
            raise
    
    async def _start_web(self):
        """Start the web platform."""
        logger.info("Starting Web Platform...")
        
        # Import Flask app
        from web.app import app
        
        port = int(os.environ.get('PORT', self.config.app_port))
        
        logger.info(f"Web platform running on port {port}")
        
        # Run Flask in background
        import threading
        flask_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=port, debug=self.config.app_debug, use_reloader=False),
            daemon=True
        )
        flask_thread.start()
        
        self.channel_isolation.log_channel_activity(Channel.WEB, "started", f"Port {port}")
    
    async def _start_telegram(self):
        """Start the Telegram bot (admin monitoring)."""
        if not self.config.telegram.bot_token:
            logger.warning("Telegram enabled but no bot token configured")
            return
        
        logger.info("Starting Telegram Bot (Admin Mode)...")
        
        try:
            from genesis_protocol.bot.telegram_bot_isolated import get_telegram_bot
            
            bot = get_telegram_bot()
            
            # Send startup alert
            self.admin_alerts.alert_deployment(
                "Genesis Protocol started",
                success=True,
                details={
                    "mode": "web_primary_telegram_admin",
                    "telegram_admin_only": self.config.telegram_admin_only
                }
            )
            
            # Run in background
            import threading
            telegram_thread = threading.Thread(target=bot.run, daemon=True)
            telegram_thread.start()
            
            self.channel_isolation.log_channel_activity(Channel.TELEGRAM, "started", "Telegram bot started")
            
        except Exception as e:
            logger.error(f"Failed to start Telegram: {e}")
            self.admin_alerts.alert_api_failure("telegram", str(e))
    
    async def stop(self):
        """Stop the application."""
        logger.info("Stopping Genesis Protocol...")
        
        self._running = False
        
        # Send shutdown alert
        self.admin_alerts.alert_deployment("Genesis Protocol stopped", success=True)
        
        self.channel_isolation.log_channel_activity(Channel.WEB, "shutdown", "Application stopped")
        
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
        await app.initialize()
        await app.start()
        
        # Keep running
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())