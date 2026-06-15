#!/usr/bin/env python3
"""Initialize database for Genesis Protocol."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import setup_logging, get_logger

setup_logging()
logger = get_logger("init_db")


def main():
    """Initialize database."""
    config = get_config()
    
    logger.info("Initializing database...")
    
    # Create data directory
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Data directory created: {data_dir}")
    
    # Initialize Redis connection test
    try:
        from genesis_protocol.memory.redis_cache import RedisCache
        cache = RedisCache()
        logger.info("Redis connection: OK")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
    
    # Initialize ChromaDB
    try:
        from genesis_protocol.memory.vector_store import VectorStore
        VectorStore()
        logger.info("ChromaDB initialized: OK")
    except Exception as e:
        logger.warning(f"ChromaDB initialization failed: {e}")
    
    logger.info("Database initialization complete!")


if __name__ == "__main__":
    main()