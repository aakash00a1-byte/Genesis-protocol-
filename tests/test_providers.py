"""Tests for AI providers."""

import pytest
from genesis_protocol.ai.providers.groq_provider import GroqProvider


class TestGroqProvider:
    """Test Groq provider."""

    def test_provider_initialization(self):
        """Test provider can be initialized."""
        provider = GroqProvider()
        assert provider is not None

    def test_provider_has_required_methods(self):
        """Test provider has required methods."""
        provider = GroqProvider()
        assert hasattr(provider, 'generate')
        assert hasattr(provider, 'generate_stream')

    def test_provider_config_check(self):
        """Test provider configuration check."""
        provider = GroqProvider()
        # Should not crash even without API key
        assert provider.is_configured() in [True, False]
