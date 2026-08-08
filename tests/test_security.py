"""Tests for genesis_protocol.security module."""

import hashlib
import hmac
import time
import pytest
from unittest.mock import patch, MagicMock


class TestAuthManager:
    """Tests for AuthManager class."""

    @pytest.fixture
    def auth_manager(self):
        """Create auth manager with mocked config."""
        with patch('genesis_protocol.security.auth.get_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.security.app_secret_key = "test-secret"
            mock_cfg.security.allowed_origins = ["http://localhost:3000"]
            mock_config.return_value = mock_cfg
            from genesis_protocol.security.auth import AuthManager
            return AuthManager()

    def test_verify_telegram_auth_empty_data(self, auth_manager):
        """Test that empty auth data returns False."""
        assert auth_manager.verify_telegram_auth({}) is False
        assert auth_manager.verify_telegram_auth(None) is False

    def test_verify_telegram_auth_expired(self, auth_manager):
        """Test that expired auth data returns False."""
        # Timestamp from 2 days ago
        old_timestamp = int(time.time()) - 172800
        auth_data = {
            "auth_date": str(old_timestamp),
            "hash": "somehash"
        }
        assert auth_manager.verify_telegram_auth(auth_data) is False

    def test_verify_telegram_auth_missing_hash(self, auth_manager):
        """Test that missing hash returns False."""
        auth_data = {
            "auth_date": str(int(time.time())),
        }
        assert auth_manager.verify_telegram_auth(auth_data) is False

    def test_verify_telegram_auth_invalid_timestamp(self, auth_manager):
        """Test that invalid timestamp returns False."""
        auth_data = {
            "auth_date": "not-a-number",
            "hash": "somehash"
        }
        assert auth_manager.verify_telegram_auth(auth_data) is False

    def test_verify_telegram_auth_valid(self, auth_manager):
        """Test valid Telegram auth verification."""
        # Build valid auth data
        auth_date = str(int(time.time()))
        auth_data = {
            "id": 123456,
            "first_name": "Test",
            "auth_date": auth_date,
        }
        
        # Build data check string
        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(auth_data.items())
        )
        
        # Calculate expected hash
        secret_key = hashlib.sha256(b"WebAppData").digest()
        expected_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        auth_data["hash"] = expected_hash
        assert auth_manager.verify_telegram_auth(auth_data) is True

    def test_is_admin_not_admin(self, auth_manager):
        """Test that user is not admin by default."""
        assert auth_manager.is_admin(12345) is False

    def test_add_admin(self, auth_manager):
        """Test adding admin user."""
        auth_manager.add_admin(12345)
        assert auth_manager.is_admin(12345) is True

    def test_remove_admin(self, auth_manager):
        """Test removing admin user."""
        auth_manager.add_admin(12345)
        auth_manager.remove_admin(12345)
        assert auth_manager.is_admin(12345) is False

    def test_check_permission_default(self, auth_manager):
        """Test default permissions for regular users."""
        # Regular user should have basic permissions
        assert auth_manager.check_permission(12345, "send_message") is True
        assert auth_manager.check_permission(12345, "use_voice") is True
        assert auth_manager.check_permission(12345, "use_images") is True
        assert auth_manager.check_permission(12345, "web_search") is True
        # Admin permission should be False
        assert auth_manager.check_permission(12345, "admin") is False
        # Unknown permission should be False
        assert auth_manager.check_permission(12345, "unknown") is False

    def test_check_permission_admin(self, auth_manager):
        """Test that admin has all permissions."""
        auth_manager.add_admin(99999)
        # Admin should have all permissions including admin
        assert auth_manager.check_permission(99999, "send_message") is True
        assert auth_manager.check_permission(99999, "admin") is True
        assert auth_manager.check_permission(99999, "unknown") is True


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware class."""

    @pytest.fixture
    def rate_limiter(self):
        """Create rate limiter for testing."""
        from genesis_protocol.security.auth import RateLimitMiddleware
        return RateLimitMiddleware(max_requests=5, window_seconds=60)

    def test_first_request_allowed(self, rate_limiter):
        """Test first request is always allowed."""
        allowed, remaining = rate_limiter.check_rate_limit("user1")
        assert allowed is True
        assert remaining == 4

    def test_within_limit(self, rate_limiter):
        """Test requests within limit are allowed."""
        # Make 5 requests (at limit)
        for i in range(5):
            allowed, _ = rate_limiter.check_rate_limit("user1")
            assert allowed is True
        
        # 6th request should be denied
        allowed, remaining = rate_limiter.check_rate_limit("user1")
        assert allowed is False
        assert remaining == 0

    def test_different_identifiers(self, rate_limiter):
        """Test rate limits are separate per identifier."""
        # Make 5 requests for user1
        for _ in range(5):
            rate_limiter.check_rate_limit("user1")
        
        # user2 should still be allowed
        allowed, remaining = rate_limiter.check_rate_limit("user2")
        assert allowed is True
        assert remaining == 4

    def test_reset_limit(self, rate_limiter):
        """Test resetting rate limit."""
        # Exhaust limit
        for _ in range(6):
            rate_limiter.check_rate_limit("user1")
        
        # Reset
        rate_limiter.reset_limit("user1")
        
        # Should be allowed again
        allowed, remaining = rate_limiter.check_rate_limit("user1")
        assert allowed is True
        assert remaining == 4

    def test_window_expiry(self, rate_limiter):
        """Test that old requests expire after window."""
        from genesis_protocol.security.auth import RateLimitMiddleware
        fast_limiter = RateLimitMiddleware(max_requests=2, window_seconds=1)
        
        # Make 2 requests (at limit)
        for _ in range(2):
            fast_limiter.check_rate_limit("user1")
        
        # 3rd should be denied
        allowed, _ = fast_limiter.check_rate_limit("user1")
        assert allowed is False
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Should be allowed again
        allowed, _ = fast_limiter.check_rate_limit("user1")
        assert allowed is True


class TestEncryptionService:
    """Tests for EncryptionService class."""

    @pytest.fixture
    def encryption_service(self):
        """Create encryption service for testing."""
        from genesis_protocol.security.encryption import EncryptionService
        return EncryptionService(key="test-key-12345")

    @pytest.fixture
    def encryption_with_mock_crypto(self):
        """Create encryption service with mocked cryptography."""
        from genesis_protocol.security.encryption import EncryptionService
        return EncryptionService(key="test-key-12345")

    def test_encrypt_decrypt_roundtrip(self, encryption_service):
        """Test encryption and decryption work together."""
        original = "Hello, World!"
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_different_each_time(self, encryption_service):
        """Test that encrypting same data gives different results (due to IV)."""
        original = "Hello, World!"
        encrypted1 = encryption_service.encrypt(original)
        encrypted2 = encryption_service.encrypt(original)
        # With proper encryption (Fernet), results should be different
        assert encrypted1 != encrypted2
        # But both should decrypt to same value
        assert encryption_service.decrypt(encrypted1) == original
        assert encryption_service.decrypt(encrypted2) == original

    def test_encrypt_unicode(self, encryption_service):
        """Test encrypting unicode text."""
        original = "Hello, 世界! 🌍"
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_long_text(self, encryption_service):
        """Test encrypting long text."""
        original = "A" * 10000
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_empty_string(self, encryption_service):
        """Test encrypting empty string."""
        original = ""
        encrypted = encryption_service.encrypt(original)
        decrypted = encryption_service.decrypt(encrypted)
        assert decrypted == original

    def test_hash_password(self, encryption_service):
        """Test password hashing."""
        password = "mysecretpassword"
        hashed = encryption_service.hash_password(password)
        
        # Hash should be different from password
        assert hashed != password
        # Hash should be base64 encoded (longer than password)
        assert len(hashed) > len(password)

    def test_verify_password_correct(self, encryption_service):
        """Test verifying correct password."""
        password = "mysecretpassword"
        hashed = encryption_service.hash_password(password)
        assert encryption_service.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self, encryption_service):
        """Test verifying incorrect password."""
        password = "mysecretpassword"
        hashed = encryption_service.hash_password(password)
        assert encryption_service.verify_password("wrongpassword", hashed) is False

    def test_verify_password_different_salts(self, encryption_service):
        """Test that same password with different salts fails verification."""
        password = "mysecretpassword"
        hashed1 = encryption_service.hash_password(password)
        hashed2 = encryption_service.hash_password(password)
        
        # Hashes should be different due to random salt
        assert hashed1 != hashed2
        # But original password should verify against both
        assert encryption_service.verify_password(password, hashed1) is True
        assert encryption_service.verify_password(password, hashed2) is True

    def test_verify_password_invalid_hash(self, encryption_service):
        """Test verifying against invalid hash."""
        assert encryption_service.verify_password("password", "invalid-hash") is False
        assert encryption_service.verify_password("password", "") is False

    def test_get_key_fingerprint(self, encryption_service):
        """Test getting key fingerprint."""
        fingerprint = encryption_service.get_key_fingerprint()
        # Should be 8 characters (first 8 of SHA256 hex)
        assert len(fingerprint) == 8
        # Should be hex characters
        assert all(c in '0123456789abcdef' for c in fingerprint)

    def test_same_key_same_fingerprint(self):
        """Test that same key produces same fingerprint."""
        from genesis_protocol.security.encryption import EncryptionService
        service1 = EncryptionService(key="same-key")
        service2 = EncryptionService(key="same-key")
        assert service1.get_key_fingerprint() == service2.get_key_fingerprint()

    def test_different_key_different_fingerprint(self):
        """Test that different keys produce different fingerprints."""
        from genesis_protocol.security.encryption import EncryptionService
        service1 = EncryptionService(key="key-one")
        service2 = EncryptionService(key="key-two")
        assert service1.get_key_fingerprint() != service2.get_key_fingerprint()

    def test_key_derivation(self):
        """Test that key is properly derived from password."""
        from genesis_protocol.security.encryption import EncryptionService
        # Same key should give same encryption
        service1 = EncryptionService(key="password123")
        service2 = EncryptionService(key="password123")
        
        encrypted = service1.encrypt("test")
        # Same password key should decrypt
        decrypted = service2.decrypt(encrypted)
        assert decrypted == "test"

    def test_generate_key_on_init(self):
        """Test that random key is generated when none provided."""
        from genesis_protocol.security.encryption import EncryptionService
        service = EncryptionService()
        # Should have a key
        assert service._key is not None
        assert len(service._key) == 32  # 256 bits
