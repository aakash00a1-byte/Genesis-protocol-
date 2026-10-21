"""Regression: AI providers must stay usable across short-lived event loops.

The Telegram webhook builds a fresh asyncio loop per request and closes it.
Providers used to cache one httpx.AsyncClient in __init__ (bound to whatever
loop first touched it), so the second request failed with "Event loop is
closed". This test drives the real provider client factory, not a mock.
"""
import asyncio

import httpx

from genesis_protocol.ai.providers.base_provider import loop_safe_client


def _client_in_new_loop(name: str) -> httpx.AsyncClient:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_get(name))
    finally:
        loop.close()


async def _get(name: str) -> httpx.AsyncClient:
    return loop_safe_client(name, base_url="https://example.invalid", timeout=5)


def test_client_survives_loop_close_and_rebinds():
    first = _client_in_new_loop("regression-provider")
    second = _client_in_new_loop("regression-provider")
    # A new loop must yield a fresh, open client -- reusing the closed one is
    # exactly the "Event loop is closed" failure.
    assert first is not second
    assert not second.is_closed


def test_client_reused_within_same_loop():
    async def both():
        a = loop_safe_client("same-loop-provider", timeout=5)
        b = loop_safe_client("same-loop-provider", timeout=5)
        return a is b

    assert asyncio.run(both()) is True
