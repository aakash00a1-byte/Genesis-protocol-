"""Genesis Protocol - Encryption Service

Encryption utilities for data protection.
"""

import base64
import hashlib
import os
from typing import Optional

from genesis_protocol.utils.logger import get_logger

logger = get_logger("security.encryption")


class EncryptionService:
    """
    Encryption service for Genesis Protocol.
    
    Provides encryption and decryption for sensitive data.
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption service.
        
        Args:
            key: Encryption key (derived from password if provided)
        """
        self._key = self._derive_key(key) if key else self._generate_key()
        logger.info("Encryption service initialized")
    
    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password."""
        return hashlib.sha256(password.encode()).digest()
    
    def _generate_key(self) -> bytes:
        """Generate random encryption key."""
        return os.urandom(32)
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt data.
        
        Args:
            data: Data to encrypt
            
        Returns:
            Base64 encoded encrypted data
        """
        try:
            from cryptography.fernet import Fernet
            
            f = Fernet(base64.urlsafe_b64encode(self._key))
            encrypted = f.encrypt(data.encode())
            
            return base64.urlsafe_b64encode(encrypted).decode()
            
        except ImportError:
            logger.warning("cryptography library not available, using simple encoding")
            encoded = base64.b64encode(data.encode())
            return encoded.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt data.
        
        Args:
            encrypted_data: Base64 encoded encrypted data
            
        Returns:
            Decrypted data
        """
        try:
            from cryptography.fernet import Fernet
            
            f = Fernet(base64.urlsafe_b64encode(self._key))
            
            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted = f.decrypt(decoded)
            
            return decrypted.decode()
            
        except ImportError:
            logger.warning("cryptography library not available, using simple decoding")
            decoded = base64.b64decode(encrypted_data.encode())
            return decoded.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise
    
    def hash_password(self, password: str) -> str:
        """
        Hash password for storage.
        
        Args:
            password: Password to hash
            
        Returns:
            Hashed password
        """
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            100000,
        )
        
        return base64.b64encode(salt + key).decode()
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Password to verify
            hashed: Stored hash
            
        Returns:
            True if password matches
        """
        try:
            decoded = base64.b64decode(hashed.encode())
            salt = decoded[:32]
            stored_key = decoded[32:]
            
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode(),
                salt,
                100000,
            )
            
            return hmac.compare_digest(key, stored_key)
            
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    def get_key_fingerprint(self) -> str:
        """
        Get fingerprint of encryption key.
        
        Returns:
            Key fingerprint (first 8 chars of SHA256)
        """
        fingerprint = hashlib.sha256(self._key).hexdigest()[:8]
        return fingerprint