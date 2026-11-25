"""Regression: the startup self-check must report the live provider list.

Before this fix ``run_startup_checks()`` called
``ProviderChain.is_provider_available('groq')``, a method that does not exist,
so every boot printed "Groq Check Error" and the check never named a provider.
"""
from __future__ import annotations

import inspect

from genesis_protocol.ai.provider_chain import ProviderChain
from genesis_protocol.ai.startup_checks import provider_line


class _Chain:
    def __init__(self, names):
        self._names = list(names)

    def get_available_providers(self):
        return list(self._names)


def test_reports_every_configured_provider():
    line = provider_line(_Chain(["gemini", "groq"]))
    assert "gemini" in line
    assert "groq" in line
    assert "error" not in line.lower()


def test_reports_no_provider_honestly():
    line = provider_line(_Chain([]))
    assert "No AI provider configured" in line
    assert "\u2705" not in line


def test_provider_chain_has_no_is_provider_available():
    """Pins the assumption the old check got wrong."""
    assert not hasattr(ProviderChain, "is_provider_available")


def test_web_startup_check_uses_the_live_provider_list():
    import web.app as app

    source = inspect.getsource(app.run_startup_checks)
    assert "is_provider_available" not in source
    assert "provider_line" in source
