"""Tests for the GLUTEN entity (evolved from GLUTTONY)."""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGlutenEntity:
    def test_create_entity(self):
        from genesis_protocol.gluten import GlutenEntity
        g = GlutenEntity()
        assert g.name == "GLUTEN"
        assert g.version == "OS"

    def test_think(self):
        from genesis_protocol.gluten import GlutenEntity
        g = GlutenEntity()
        result = g.think("Hello")
        assert result["entity"] == "GLUTEN"
        assert "layers" in result

    def test_observe(self):
        from genesis_protocol.gluten import GlutenEntity
        g = GlutenEntity()
        obs = g.observe()
        assert obs["name"] == "GLUTEN"
        assert "layers" in obs

    def test_status(self):
        from genesis_protocol.gluten import GlutenEntity
        g = GlutenEntity()
        status = g.status()
        assert "GLUTEN" in status
        assert "OS" in status


class TestIdentity:
    def test_greet(self):
        from genesis_protocol.gluten import Identity
        identity = Identity()
        greeting = identity.greet()
        assert "GLUTEN" in greeting
        assert "Gluten" in greeting

    def test_describe_self(self):
        from genesis_protocol.gluten import Identity
        identity = Identity()
        desc = identity.describe_self()
        assert "GLUTEN" in desc
        assert "Genesis Protocol" in desc

    def test_get_identity(self):
        from genesis_protocol.gluten import Identity
        identity = Identity()
        info = identity.get_identity()
        assert info["name"] == "GLUTEN"
        assert info["nickname"] == "Gluten"


class TestIntegration:
    def test_get_gluten_singleton(self):
        from genesis_protocol.gluten import get_gluten
        g1 = get_gluten()
        g2 = get_gluten()
        assert g1 is g2

    def test_get_identity_singleton(self):
        from genesis_protocol.gluten import get_identity
        i1 = get_identity()
        i2 = get_identity()
        assert i1 is i2

    def test_evolution_chain(self):
        from genesis_protocol.gluten import Identity, EVOLUTION_CHAIN
        assert EVOLUTION_CHAIN == ["GENESIS", "GLUTTONY", "GLUTEN"]
        assert Identity().lineage() == "GENESIS -> GLUTTONY -> GLUTEN"
