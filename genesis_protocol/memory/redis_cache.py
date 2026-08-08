"""Genesis Protocol - Redis Cache

Redis caching layer for session data and fast access.
"""

import json
from datetime import datetime
from typing import Optional, Any

import redis.asyncio as redis

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("memory.redis_cache")


class RedisCache:
    """
    Redis-based caching for Genesis Protocol.
    
    Provides fast key-value storage with TTL support.
    Uses in-memory fallback when Redis is unavailable.
    """
    
    _instance: Optional["RedisCache"] = None
    _client: Optional[redis.Redis] = None
    _fallback_cache: dict = {}
    _fallback_ttl: dict = {}
    
    def __new__(cls):
        """Singleton pattern for Redis connection."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize Redis cache."""
        if self._client is not None:
            return
        
        config = get_config()
        
        try:
            self._client = redis.Redis(
                host=config.memory.redis_host,
                port=config.memory.redis_port,
                password=config.memory.redis_password or None,
                db=config.memory.redis_db,
                decode_responses=True,
            )
            logger.info(
                "Redis cache initialized",
                host=config.memory.redis_host,
                port=config.memory.redis_port
            )
        except Exception as e:
            logger.warning(f"Redis unavailable, using in-memory fallback: {e}")
            self._client = None
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if self._client:
            try:
                value = await self._client.get(key)
                if value:
                    logger.debug(f"Cache hit: {key}")
                else:
                    logger.debug(f"Cache miss: {key}")
                return value
            except Exception as e:
                logger.warning(f"Redis get failed, using fallback: {e}")
        
        # Fallback to in-memory cache
        return self._fallback_get(key)
    
    def _fallback_get(self, key: str) -> Optional[str]:
        """In-memory fallback for get."""
        if key in self._fallback_cache:
            import time
            expiry = self._fallback_ttl.get(key)
            if expiry and time.time() > expiry:
                del self._fallback_cache[key]
                del self._fallback_ttl[key]
                return None
            return self._fallback_cache.get(key)
        return None
    
    async def set(self, key: str, value: str, ttl: int = 86400):
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: 24 hours)
        """
        if self._client:
            try:
                await self._client.setex(key, ttl, value)
                logger.debug(f"Cache set: {key} (ttl={ttl}s)")
                return
            except Exception as e:
                logger.warning(f"Redis set failed, using fallback: {e}")
        
        # Fallback to in-memory cache
        import time
        self._fallback_cache[key] = value
        self._fallback_ttl[key] = time.time() + ttl
        logger.debug(f"Fallback cache set: {key} (ttl={ttl}s)")
    
    def _fallback_delete(self, key: str):
        """In-memory fallback for delete."""
        self._fallback_cache.pop(key, None)
        self._fallback_ttl.pop(key, None)
    
    async def delete(self, key: str):
        """
        Delete key from cache.
        
        Args:
            key: Cache key
        """
        if self._client:
            try:
                await self._client.delete(key)
                logger.debug(f"Cache delete: {key}")
                return
            except Exception as e:
                logger.warning(f"Redis delete failed, using fallback: {e}")
        
        self._fallback_delete(key)
        logger.debug(f"Fallback cache delete: {key}")
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists
        """
        if not self._client:
            return False
        
        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    async def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Parsed JSON or None
        """
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None
    
    async def set_json(self, key: str, value: Any, ttl: int = 86400):
        """
        Set JSON value in cache.
        
        Args:
            key: Cache key
            value: JSON-serializable value
            ttl: Time to live in seconds
        """
        json_str = json.dumps(value)
        await self.set(key, json_str, ttl)
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """
        Increment a counter.
        
        Args:
            key: Cache key
            amount: Amount to increment
            
        Returns:
            New value
        """
        if not self._client:
            return 0
        
        try:
            return await self._client.incrby(key, amount)
        except Exception as e:
            logger.error(f"Redis increment error: {e}")
            return 0
    
    async def get_ttl(self, key: str) -> int:
        """
        Get remaining TTL for key.
        
        Args:
            key: Cache key
            
        Returns:
            TTL in seconds, -1 if no TTL, -2 if key doesn't exist
        """
        if not self._client:
            return -2
        
        try:
            return await self._client.ttl(key)
        except Exception as e:
            logger.error(f"Redis ttl error: {e}")
            return -2
    
    async def clear_expired(self):
        """Clear expired keys (handled automatically by Redis)."""
        pass
    
    async def ping(self) -> bool:
        """
        Check Redis connection.
        
        Returns:
            True if connected
        """
        if not self._client:
            return False
        
        try:
            await self._client.ping()
            return True
        except Exception:
            return False
    
    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")