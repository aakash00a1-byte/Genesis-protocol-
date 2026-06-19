"""Tests for v2.0 GLUTTONY Entity"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGluttonyEntity:
    def test_create_entity(self):
        from genesis_protocol.gluttony import GluttonyEntity
        g = GluttonyEntity()
        assert g.name == "GLUTTONY"
        assert g.version == "2.0"

    def test_think(self):
        from genesis_protocol.gluttony import GluttonyEntity
        g = GluttonyEntity()
        result = g.think("Hello")
        assert result["entity"] == "GLUTTONY"
        assert "layers_active" in result

    def test_observe(self):
        from genesis_protocol.gluttony import GluttonyEntity
        g = GluttonyEntity()
        obs = g.observe()
        assert obs["name"] == "GLUTTONY"
        assert "layers" in obs

    def test_status(self):
        from genesis_protocol.gluttony import GluttonyEntity
        g = GluttonyEntity()
        status = g.status()
        assert "GLUTTONY" in status
        assert "2.0" in status


class TestIdentity:
    def test_greet(self):
        from genesis_protocol.gluttony import Identity
        identity = Identity()
        greeting = identity.greet()
        assert "GLUTTONY" in greeting
        assert "Gluten" in greeting

    def test_describe_self(self):
        from genesis_protocol.gluttony import Identity
        identity = Identity()
        desc = identity.describe_self()
        assert "GLUTTONY" in desc
        assert "Genesis Protocol" in desc

    def test_get_identity(self):
        from genesis_protocol.gluttony import Identity
        identity = Identity()
        info = identity.get_identity()
        assert info["name"] == "GLUTTONY"
        assert info["nickname"] == "Gluten"


class TestIntegration:
    def test_get_gluttony_singleton(self):
        from genesis_protocol.gluttony import get_gluttony
        g1 = get_gluttony()
        g2 = get_gluttony()
        assert g1 is g2

    def test_get_identity_singleton(self):
        from genesis_protocol.gluttony import get_identity
        i1 = get_identity()
        i2 = get_identity()
        assert i1 is i2
