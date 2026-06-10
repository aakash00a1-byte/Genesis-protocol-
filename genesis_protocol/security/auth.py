"""Genesis Protocol - Authentication and Authorization

Security layer for Genesis Protocol.
"""

import hashlib
import hmac
import time
from typing import Optional, Dict, List

from genesis_protocol.config import get_config
from genesis_protocol.utils.logger import get_logger

logger = get_logger("security.auth")


class AuthManager:
    """
    Authentication and authorization manager.
    
    Handles user authentication and permission management.
    """
    
    def __init__(self):
        """Initialize auth manager."""
        config = get_config()
        self.secret_key = config.security.app_secret_key or "default-secret-key"
        self.allowed_origins = config.security.allowed_origins
        
        # Admin user IDs (configured via env)
        self.admin_users: set = set()
        
        logger.info("Auth manager initialized")
    
    def verify_telegram_auth(self, auth_data: Dict) -> bool:
        """
        Verify Telegram authentication data.
        
        Args:
            auth_data: Telegram auth data dictionary
            
        Returns:
            True if authentication is valid
        """
        if not auth_data:
            return False
        
        # Check timestamp (should be within 24 hours)
        auth_date = auth_data.get("auth_date")
        if auth_date:
            try:
                timestamp = int(auth_date)
                current = int(time.time())
                
                if current - timestamp > 86400:  # 24 hours
                    logger.warning("Telegram auth data expired")
                    return False
            except ValueError:
                return False
        
        # Verify hash
        received_hash = auth_data.get("hash")
        if not received_hash:
            return False
        
        # Build data check string
        data_check_string = "\n".join(
            f"{key}={value}" 
            for key, value in sorted(auth_data.items()) 
            if key != "hash"
        )
        
        # Calculate expected hash
        secret_key = hashlib.sha256(b"WebAppData").digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(received_hash, expected_hash)
    
    def is_admin(self, user_id: int) -> bool:
        """
        Check if user is an admin.
        
        Args:
            user_id: User ID
            
        Returns:
            True if user is admin
        """
        return user_id in self.admin_users
    
    def add_admin(self, user_id: int):
        """Add admin user."""
        self.admin_users.add(user_id)
        logger.info(f"Admin added: {user_id}")
    
    def remove_admin(self, user_id: int):
        """Remove admin user."""
        self.admin_users.discard(user_id)
        logger.info(f"Admin removed: {user_id}")
    
    def check_permission(self, user_id: int, permission: str) -> bool:
        """
        Check user permission.
        
        Args:
            user_id: User ID
            permission: Permission name
            
        Returns:
            True if user has permission
        """
        # Admins have all permissions
        if self.is_admin(user_id):
            return True
        
        # Default permissions
        default_permissions = {
            "send_message": True,
            "use_voice": True,
            "use_images": True,
            "web_search": True,
            "admin": False,
        }
        
        return default_permissions.get(permission, False)


class RateLimitMiddleware:
    """
    Rate limiting middleware for API protection.
    
    Provides per-user and per-endpoint rate limiting.
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        """
        Initialize rate limit middleware.
        
        Args:
            max_requests: Maximum requests per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
        
        logger.info(f"Rate limit middleware initialized ({max_requests}/{window_seconds}s)")
    
    def check_rate_limit(self, identifier: str) -> tuple[bool, int]:
        """
        Check if request is within rate limit.
        
        Args:
            identifier: User or endpoint identifier
            
        Returns:
            tuple: (allowed, remaining_requests)
        """
        current_time = time.time()
        
        if identifier not in self._requests:
            self._requests[identifier] = []
        
        # Remove old requests outside window
        self._requests[identifier] = [
            ts for ts in self._requests[identifier]
            if current_time - ts < self.window_seconds
        ]
        
        # Check limit
        if len(self._requests[identifier]) >= self.max_requests:
            return False, 0
        
        # Add current request
        self._requests[identifier].append(current_time)
        
        remaining = self.max_requests - len(self._requests[identifier])
        
        return True, remaining
    
    def reset_limit(self, identifier: str):
        """Reset rate limit for identifier."""
        if identifier in self._requests:
            self._requests[identifier] = []
            logger.info(f"Rate limit reset: {identifier}")