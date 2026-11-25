"""Startup provider reporting.

The web startup self-check asked the provider chain for
``is_provider_available('groq')``. That method does not exist on
``ProviderChain`` (the scoring engine has one, with a different signature), so
the check raised ``AttributeError`` on every boot, printed "Groq Check Error"
and never named a provider - even when several were configured. It also
hardcoded Groq while the live default is a Gemini model.

Reporting now reads the live provider list, so the log can only name a provider
that is actually configured, and never a hardcoded one.
"""
from __future__ import annotations

from typing import Any


def provider_line(chain: Any | None = None) -> str:
    """Return one line naming the AI providers that are actually configured."""
    if chain is None:
        from genesis_protocol.ai.provider_chain import get_provider_chain

        chain = get_provider_chain()
    available = list(chain.get_available_providers())
    if available:
        return f"   \u2705 AI providers available: {', '.join(available)}"
    return "   \u26a0\ufe0f  No AI provider configured (set an API key)"
