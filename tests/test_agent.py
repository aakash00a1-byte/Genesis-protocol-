"""Tests for genesis_protocol.ai.agent module."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio


class TestGenesisAgent:
    """Tests for GenesisAgent class."""

    def test_agent_import(self):
        """Test agent can be imported."""
        from genesis_protocol.ai.agent import GenesisAgent
        assert GenesisAgent is not None

    def test_process_is_async(self):
        """Test process method exists and is async."""
        from genesis_protocol.ai.agent import GenesisAgent
        import inspect
        assert hasattr(GenesisAgent, 'process')
        assert inspect.iscoroutinefunction(GenesisAgent.process)

    def test_process_signature(self):
        """Test process method has correct signature."""
        from genesis_protocol.ai.agent import GenesisAgent
        import inspect
        sig = inspect.signature(GenesisAgent.process)
        params = list(sig.parameters.keys())
        
        # Check required parameters exist
        assert 'self' in params
        assert 'query' in params
        assert 'chat_id' in params
        assert 'user_id' in params


class TestProviderChain:
    """Tests for ProviderChain class."""

    def test_provider_chain_initialization(self):
        """Test provider chain initializes."""
        with patch('genesis_protocol.ai.provider_chain.get_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.providers.openai.api_key = "test-key"
            mock_cfg.providers.gemini.api_key = "test-key"
            mock_cfg.providers.groq.api_key = "test-key"
            mock_cfg.providers.deepseek.api_key = "test-key"
            mock_cfg.providers.mistral.api_key = "test-key"
            mock_cfg.logging.level = "INFO"
            mock_config.return_value = mock_cfg
            
            from genesis_protocol.ai.provider_chain import ProviderChain
            chain = ProviderChain()
            
            assert chain is not None
            assert hasattr(chain, '_base_order')

    def test_base_order_exists(self):
        """Test _base_order attribute exists and is a list."""
        with patch('genesis_protocol.ai.provider_chain.get_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.providers.openai.api_key = "test-key"
            mock_cfg.providers.gemini.api_key = "test-key"
            mock_cfg.providers.groq.api_key = "test-key"
            mock_cfg.providers.deepseek.api_key = "test-key"
            mock_cfg.providers.mistral.api_key = "test-key"
            mock_cfg.logging.level = "INFO"
            mock_config.return_value = mock_cfg
            
            from genesis_protocol.ai.provider_chain import ProviderChain
            chain = ProviderChain()
            
            assert hasattr(chain, '_base_order')
            assert isinstance(chain._base_order, list)
            assert len(chain._base_order) > 0

    def test_get_available_providers(self):
        """Test getting available providers."""
        with patch('genesis_protocol.ai.provider_chain.get_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.providers.openai.api_key = "test-key"
            mock_cfg.providers.gemini.api_key = "test-key"
            mock_cfg.providers.groq.api_key = "test-key"
            mock_cfg.providers.deepseek.api_key = "test-key"
            mock_cfg.providers.mistral.api_key = "test-key"
            mock_cfg.logging.level = "INFO"
            mock_config.return_value = mock_cfg
            
            from genesis_protocol.ai.provider_chain import ProviderChain
            chain = ProviderChain()
            
            providers = chain.get_available_providers()
            assert isinstance(providers, list)

    def test_get_status(self):
        """Test getting chain status."""
        with patch('genesis_protocol.ai.provider_chain.get_config') as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.providers.openai.api_key = "test-key"
            mock_cfg.providers.gemini.api_key = "test-key"
            mock_cfg.providers.groq.api_key = "test-key"
            mock_cfg.providers.deepseek.api_key = "test-key"
            mock_cfg.providers.mistral.api_key = "test-key"
            mock_cfg.logging.level = "INFO"
            mock_config.return_value = mock_cfg
            
            from genesis_protocol.ai.provider_chain import ProviderChain
            chain = ProviderChain()
            
            status = chain.get_status()
            assert isinstance(status, dict)
