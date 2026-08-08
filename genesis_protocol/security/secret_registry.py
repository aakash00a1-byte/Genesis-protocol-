"""Genesis Protocol - Secret Registry

Secure credential and secret management.
Based on OpenHands secret registry pattern.
"""

import os
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger("secret_registry")


class SecretType(Enum):
    """Types of secrets."""
    API_KEY = "api_key"
    PASSWORD = "password"
    TOKEN = "token"
    CREDENTIAL = "credential"
    CERTIFICATE = "certificate"
    SSH_KEY = "ssh_key"


@dataclass
class Secret:
    """A registered secret."""
    name: str
    secret_type: SecretType
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: Optional[datetime] = None
    use_count: int = 0
    masked: bool = True  # Whether to mask in logs


class SecretRegistry:
    """
    Secure secret management for Genesis Protocol.
    
    Features:
    - Register and manage secrets
    - Environment variable integration
    - Secure retrieval with masking
    - Usage tracking
    - Access control
    """
    
    # Common secret names
    WELL_KNOWN_SECRETS = {
        "GROQ_API_KEY": SecretType.API_KEY,
        "OPENAI_API_KEY": SecretType.API_KEY,
        "ANTHROPIC_API_KEY": SecretType.API_KEY,
        "GEMINI_API_KEY": SecretType.API_KEY,
        "TELEGRAM_BOT_TOKEN": SecretType.TOKEN,
        "DISCORD_BOT_TOKEN": SecretType.TOKEN,
        "DATABASE_URL": SecretType.CREDENTIAL,
        "REDIS_URL": SecretType.CREDENTIAL,
        "SECRET_KEY": SecretType.CREDENTIAL,
    }
    
    def __init__(self):
        """Initialize secret registry."""
        self._secrets: Dict[str, Secret] = {}
        self._values: Dict[str, str] = {}
        self._masked_values: Dict[str, str] = {}
        self._load_from_env()
        logger.info("SecretRegistry initialized")
    
    def _load_from_env(self):
        """Load known secrets from environment variables."""
        for name, secret_type in self.WELL_KNOWN_SECRETS.items():
            value = os.environ.get(name)
            if value:
                self.register(name, value, secret_type)
    
    def register(self, name: str, value: str, 
                 secret_type: SecretType = SecretType.API_KEY,
                 description: str = "",
                 masked: bool = True):
        """
        Register a secret.
        
        Args:
            name: Secret name
            value: Secret value
            secret_type: Type of secret
            description: Optional description
            masked: Whether to mask in logs
        """
        self._secrets[name] = Secret(
            name=name,
            secret_type=secret_type,
            description=description,
            masked=masked
        )
        self._values[name] = value
        self._masked_values[name] = self._mask_value(value)
        
        logger.debug(f"Registered secret: {name}")
    
    def get(self, name: str) -> Optional[str]:
        """
        Get a secret value.
        
        Args:
            name: Secret name
            
        Returns:
            Secret value or None if not found
        """
        # Check registered secrets first
        if name in self._values:
            secret = self._secrets[name]
            secret.last_used = datetime.utcnow()
            secret.use_count += 1
            return self._values[name]
        
        # Fall back to environment variable
        value = os.environ.get(name)
        if value:
            # Auto-register if not already
            if name not in self._secrets:
                secret_type = self.WELL_KNOWN_SECRETS.get(name, SecretType.API_KEY)
                self.register(name, value, secret_type)
            return value
        
        return None
    
    def get_or_raise(self, name: str) -> str:
        """
        Get a secret or raise if not found.
        
        Args:
            name: Secret name
            
        Returns:
            Secret value
            
        Raises:
            ValueError: If secret not found
        """
        value = self.get(name)
        if value is None:
            raise ValueError(f"Secret not found: {name}")
        return value
    
    def _mask_value(self, value: str, visible_chars: int = 4) -> str:
        """Mask a secret value."""
        if len(value) <= visible_chars * 2:
            return "*" * len(value)
        return value[:visible_chars] + "*" * (len(value) - visible_chars * 2) + value[-visible_chars:]
    
    def get_masked(self, name: str) -> str:
        """Get masked version of a secret."""
        if name in self._masked_values:
            return self._masked_values[name]
        
        value = os.environ.get(name, "")
        return self._mask_value(value)
    
    def list_secrets(self) -> List[Dict[str, Any]]:
        """List all registered secrets (masked)."""
        return [
            {
                "name": name,
                "type": secret.secret_type.value,
                "description": secret.description,
                "masked_value": self.get_masked(name),
                "created_at": secret.created_at.isoformat(),
                "last_used": secret.last_used.isoformat() if secret.last_used else None,
                "use_count": secret.use_count
            }
            for name, secret in self._secrets.items()
        ]
    
    def list_from_env(self) -> List[str]:
        """List all secret names from environment."""
        secrets = []
        for name in os.environ:
            if any(x in name.upper() for x in ["KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"]):
                secrets.append(name)
        return secrets
    
    def update(self, name: str, value: str):
        """Update a secret value."""
        if name in self._secrets:
            self._values[name] = value
            self._masked_values[name] = self._mask_value(value)
            logger.info(f"Updated secret: {name}")
        else:
            self.register(name, value)
    
    def delete(self, name: str) -> bool:
        """Delete a secret."""
        if name in self._secrets:
            del self._secrets[name]
            self._values.pop(name, None)
            self._masked_values.pop(name, None)
            logger.info(f"Deleted secret: {name}")
            return True
        return False
    
    def exists(self, name: str) -> bool:
        """Check if a secret exists."""
        return name in self._values or name in os.environ
    
    def get_fingerprint(self, name: str) -> str:
        """Get a hash fingerprint of a secret for identification."""
        value = self.get(name)
        if value:
            return hashlib.sha256(value.encode()).hexdigest()[:8]
        return ""
    
    def check_health(self) -> Dict[str, Any]:
        """Check health of all secrets."""
        results = {
            "total": len(self._secrets),
            "missing_critical": [],
            "warnings": []
        }
        
        # Check critical secrets
        critical = ["GROQ_API_KEY", "TELEGRAM_BOT_TOKEN"]
        for name in critical:
            if not self.exists(name):
                results["missing_critical"].append(name)
        
        # Check for weak secrets
        for name, secret in self._secrets.items():
            value = self._values.get(name, "")
            if len(value) < 10:
                results["warnings"].append(f"{name} appears to be weak/short")
        
        return results


# Singleton
_secret_registry: Optional[SecretRegistry] = None


def get_secret_registry() -> SecretRegistry:
    """Get global secret registry."""
    global _secret_registry
    if _secret_registry is None:
        _secret_registry = SecretRegistry()
    return _secret_registry


# Convenience decorators
def require_secret(name: str):
    """Decorator to require a secret for a function."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            registry = get_secret_registry()
            if not registry.exists(name):
                raise ValueError(f"Required secret not found: {name}")
            return func(*args, **kwargs)
        return wrapper
    return decorator
