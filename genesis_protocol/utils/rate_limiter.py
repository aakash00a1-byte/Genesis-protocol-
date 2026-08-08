"""Genesis Protocol - Rate Limiter

Token bucket rate limiting for API calls and user requests.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from genesis_protocol.utils.logger import get_logger

logger = get_logger("rate_limiter")


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int
    requests_per_hour: int
    burst_size: int = 5


class TokenBucket:
    """Token bucket algorithm implementation."""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum tokens (bucket size)
            refill_rate: Tokens per second
        """
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate
        self.last_refill = time.time()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            bool: True if tokens available, False otherwise
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now
    
    def wait_time(self, tokens: int = 1) -> float:
        """
        Calculate wait time for tokens.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            float: Seconds to wait
        """
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        needed = tokens - self.tokens
        return needed / self.refill_rate


class RateLimiter:
    """
    Multi-tier rate limiter for Genesis Protocol.
    
    Supports per-user, per-provider, and global rate limiting.
    """
    
    def __init__(self):
        """Initialize rate limiter."""
        self._user_buckets: dict[int, dict[str, TokenBucket]] = defaultdict(dict)
        self._provider_buckets: dict[str, TokenBucket] = {}
        self._global_bucket: Optional[TokenBucket] = None
        
        # Configuration
        self._user_rpm = 20
        self._user_rph = 500
        self._provider_rpm = 30
        self._global_rpm = 100
        
        logger.info("Rate limiter initialized")
    
    def _get_user_bucket(self, user_id: int, window: str) -> TokenBucket:
        """Get or create user bucket for window."""
        if user_id not in self._user_buckets:
            self._user_buckets[user_id] = {}
        
        if window not in self._user_buckets[user_id]:
            if window == "minute":
                capacity = self._user_rpm
                refill_rate = capacity / 60.0
            else:  # hour
                capacity = self._user_rph
                refill_rate = capacity / 3600.0
            
            self._user_buckets[user_id][window] = TokenBucket(capacity, refill_rate)
        
        return self._user_buckets[user_id][window]
    
    def _get_provider_bucket(self, provider: str) -> TokenBucket:
        """Get or create provider bucket."""
        if provider not in self._provider_buckets:
            # Different providers have different limits
            limits = {
                "groq": 30,
                "openai": 500,
                "gemini": 60,
                "huggingface": 20,
            }
            rpm = limits.get(provider, 30)
            self._provider_buckets[provider] = TokenBucket(rpm, rpm / 60.0)
        
        return self._provider_buckets[provider]
    
    def _get_global_bucket(self) -> TokenBucket:
        """Get or create global bucket."""
        if self._global_bucket is None:
            self._global_bucket = TokenBucket(self._global_rpm, self._global_rpm / 60.0)
        return self._global_bucket
    
    def check_user_limit(self, user_id: int) -> tuple[bool, float]:
        """
        Check if user is within rate limits.
        
        Args:
            user_id: User ID
            
        Returns:
            tuple: (allowed, wait_time_seconds)
        """
        minute_bucket = self._get_user_bucket(user_id, "minute")
        hour_bucket = self._get_user_bucket(user_id, "hour")
        
        if not minute_bucket.consume():
            return False, minute_bucket.wait_time()
        
        if not hour_bucket.consume():
            return False, hour_bucket.wait_time()
        
        return True, 0.0
    
    def check_provider_limit(self, provider: str) -> tuple[bool, float]:
        """
        Check if provider is within rate limits.
        
        Args:
            provider: Provider name
            
        Returns:
            tuple: (allowed, wait_time_seconds)
        """
        bucket = self._get_provider_bucket(provider)
        
        if not bucket.consume():
            return False, bucket.wait_time()
        
        return True, 0.0
    
    def check_global_limit(self) -> tuple[bool, float]:
        """
        Check if global rate limit allows request.
        
        Returns:
            tuple: (allowed, wait_time_seconds)
        """
        bucket = self._get_global_bucket()
        
        if not bucket.consume():
            return False, bucket.wait_time()
        
        return True, 0.0
    
    def check_all(self, user_id: int, provider: str) -> tuple[bool, str, float]:
        """
        Check all rate limits.
        
        Args:
            user_id: User ID
            provider: Provider name
            
        Returns:
            tuple: (allowed, reason, wait_time_seconds)
        """
        # Check global first
        allowed, wait = self.check_global_limit()
        if not allowed:
            return False, "global_rate_limit", wait
        
        # Check user limits
        allowed, wait = self.check_user_limit(user_id)
        if not allowed:
            return False, "user_rate_limit", wait
        
        # Check provider limits
        allowed, wait = self.check_provider_limit(provider)
        if not allowed:
            return False, f"provider_rate_limit_{provider}", wait
        
        return True, "", 0.0
    
    def reset_user(self, user_id: int):
        """Reset rate limits for a user."""
        if user_id in self._user_buckets:
            del self._user_buckets[user_id]
            logger.info(f"Reset rate limits for user {user_id}")
    
    def reset_provider(self, provider: str):
        """Reset rate limits for a provider."""
        if provider in self._provider_buckets:
            del self._provider_buckets[provider]
            logger.info(f"Reset rate limits for provider {provider}")
    
    def get_status(self, user_id: int) -> dict:
        """Get rate limit status for user."""
        minute_bucket = self._get_user_bucket(user_id, "minute")
        hour_bucket = self._get_user_bucket(user_id, "hour")
        
        return {
            "user_id": user_id,
            "minute_remaining": int(minute_bucket.tokens),
            "minute_capacity": minute_bucket.capacity,
            "hour_remaining": int(hour_bucket.tokens),
            "hour_capacity": hour_bucket.capacity,
        }


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter