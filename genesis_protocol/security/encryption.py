"""Genesis Protocol - Encryption Service

Encryption utilities for data protection.
"""

import base64
import hashlib
import hmac
import os
from typing import Optional

from genesis_protocol.utils.logger import get_logger

logger = get_logger("security.encryption")


class EncryptionUnavailableError(RuntimeError):
    """Raised when the ``cryptography`` backend is missing.

    The service must fail closed: silently falling back to base64 would make
    callers believe their data is encrypted when it is merely encoded.
    """


LEGACY_CIPHERTEXT_HINT = (
    "ciphertext cannot be decrypted with this key: either the password/key is "
    "wrong, or the data was sealed by an older key derivation (single SHA-256, "
    "or PBKDF2 with 200,000 iterations). Legacy backups must be re-encrypted: "
    "see docs/security/V7_SECURITY_RECOVERY.md (backup migration) and run "
    "scripts/migrate_backup_vault.py."
)


class LegacyCiphertextError(RuntimeError):
    """Raised when a blob was sealed by an older key derivation.

    Reported separately from a wrong password because the fix differs: a wrong
    key is a configuration error, while legacy ciphertext needs migration
    (``scripts/migrate_backup_vault.py``). The key derivation has changed twice
    (single SHA-256 -> PBKDF2 200k -> PBKDF2 600k), so old backups must be
    re-encrypted rather than silently dropped.
    """


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

    # PBKDF2-HMAC-SHA256 rather than a single SHA-256: a plain digest is a fast
    # hash, not a key-derivation function, so a leaked ciphertext could be
    # attacked at GPU speed. 600,000 iterations is the OWASP Password Storage
    # Cheat Sheet figure for PBKDF2-HMAC-SHA256 (verified 2026-11-25).
    #
    # The salt is a fixed domain-separation constant rather than random because
    # derivation must stay deterministic across restarts -- the same password
    # has to reproduce the same key, or stored ciphertext becomes unreadable.
    # A per-install random salt needs a versioned ciphertext format first; the
    # design and its migration plan are written up in
    # docs/security/V7_SECURITY_RECOVERY.md ("Per-install salt") and are NOT
    # implemented yet, because changing the format without a migration would
    # strand existing backups.
    _KDF_ITERATIONS = 600_000
    _KDF_SALT_CONTEXT = b"genesis-protocol/encryption/v2"

    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password (PBKDF2-HMAC-SHA256)."""
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode(), self._KDF_SALT_CONTEXT, self._KDF_ITERATIONS, dklen=32
        )
    
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
            
        except ImportError as exc:
            logger.error("cryptography library not available; refusing to fake encryption")
            raise EncryptionUnavailableError(
                "The 'cryptography' package is required for encryption. "
                "Install it (it is listed in requirements.txt) instead of relying "
                "on an unencrypted fallback."
            ) from exc
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
            from cryptography.fernet import Fernet, InvalidToken

            decoded = base64.urlsafe_b64decode(encrypted_data.encode())
            try:
                decrypted = Fernet(base64.urlsafe_b64encode(self._key)).decrypt(decoded)
            except InvalidToken as exc:
                # Indistinguishable from a wrong password at the cipher level, so
                # the message names both causes and the migration tool.
                raise LegacyCiphertextError(LEGACY_CIPHERTEXT_HINT) from exc

            return decrypted.decode()

        except ImportError as exc:
            logger.error("cryptography library not available; cannot decrypt")
            raise EncryptionUnavailableError(
                "The 'cryptography' package is required for decryption. "
                "Install it (it is listed in requirements.txt) instead of relying "
                "on an unencrypted fallback."
            ) from exc
        except LegacyCiphertextError:
            raise
        except Exception as e:
            logger.error(f"Decryption failed: {type(e).__name__}")
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


def encrypt_with_raw_key(data: str, key: bytes) -> str:
    """Seal ``data`` with a caller-supplied 32-byte key.

    Migration-only: it lets ``scripts/migrate_backup_vault.py`` (and its tests)
    reproduce a container sealed by a key this process cannot derive -- a
    pre-v7 ``sha256(password)`` key, or the 200k-iteration key of an
    intermediate build. The normal path is ``EncryptionService``.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise EncryptionUnavailableError(
            "The 'cryptography' package is required for encryption."
        ) from exc
    if len(key) != 32:
        raise ValueError("raw encryption keys must be 32 bytes")
    token = Fernet(base64.urlsafe_b64encode(key)).encrypt(data.encode())
    return base64.urlsafe_b64encode(token).decode()


def decrypt_with_raw_key(encrypted_data: str, key: bytes) -> str:
    """Open a blob sealed with ``encrypt_with_raw_key`` (migration-only)."""
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:
        raise EncryptionUnavailableError(
            "The 'cryptography' package is required for decryption."
        ) from exc
    if len(key) != 32:
        raise ValueError("raw encryption keys must be 32 bytes")
    try:
        token = base64.urlsafe_b64decode(encrypted_data.encode())
        return Fernet(base64.urlsafe_b64encode(key)).decrypt(token).decode()
    except InvalidToken as exc:
        raise LegacyCiphertextError(
            "the supplied legacy key does not open this ciphertext"
        ) from exc
