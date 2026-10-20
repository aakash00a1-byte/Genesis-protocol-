"""Live provider path: the stdlib transport actually reaches a provider.

The adapters used to import ``requests`` (a third-party dependency that is not
shipped). They now use ``urllib`` through ``default_post``/``default_get``, so a
live run works with no extra dependency. These tests drive the real transport
against a local HTTP server — no external network.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from genesis.adapters.registration import register_default_adapters
from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.providers.base import ModelCapability
from genesis.providers.factory import get_factory


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep the console quiet
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0) or 0)
        self.rfile.read(length)
        self.server.last_auth = self.headers.get("Authorization", "")
        body = json.dumps(
            {
                "choices": [{"message": {"content": "hello from urllib"}}],
                "usage": {"total_tokens": 3},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.last_auth = ""
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()


@pytest.fixture
def configured(server, monkeypatch):
    port = server.server_address[1]
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GENESIS_OPENAI_COMPAT_MODEL", "live-model")
    register_default_adapters()
    return server


def test_stdlib_transport_reaches_a_live_endpoint(configured) -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=False)
    kernel = build(cfg)
    result = kernel.complete("say hi", ModelCapability.CHAT, offline=False)
    assert result.output == "hello from urllib"
    assert result.provider == "openai_compat"
    # The key was sent in the Authorization header, not in the result.
    assert configured.last_auth == "Bearer test-key-not-real"
    assert "test-key-not-real" not in str(result.to_dict())


def test_online_router_selects_the_configured_provider(configured) -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=False)
    kernel = build(cfg)
    decision = kernel.router.route(ModelCapability.CHAT, offline=False)
    assert decision.provider == "openai_compat"


def test_unconfigured_provider_reports_disabled() -> None:
    register_default_adapters()
    health = get_factory().health("openai_compat", GenesisConfig(env=Env.TESTING))
    assert health.ok is False
    assert health.status.value == "disabled"
