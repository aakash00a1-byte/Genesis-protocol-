#!/usr/bin/env python3
"""Genesis Protocol - Discord Bot Runner

Starts the Discord bot as a standalone service.
"""

import sys
import os
import asyncio
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
)

from genesis_protocol.utils.logger import setup_logging
setup_logging()

from genesis_protocol.bot.discord_bot import DiscordBot, run_discord_bot

if __name__ == "__main__":
    run_discord_bot()
