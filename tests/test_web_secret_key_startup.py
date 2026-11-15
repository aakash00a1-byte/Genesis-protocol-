"""Production startup must never sign sessions with a guessable key.

``web/app.py`` resolves ``SECRET_KEY`` at import time via ``_resolve_secret_key``.
A known default (or a missing/short key) makes session cookies and mobile bearer
tokens forgeable by anyone. These tests pin the contract:

* production (a hosting marker or ``GENESIS_ENV=production``) with a missing,
  known-insecure or too-short key refuses to start;
* production with a strong key starts and uses it;
* local development never falls back to the public default — it gets a fresh
  random per-process key, and the secret is never printed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import web.app as appmod  # noqa: E402

STRONG_KEY = "8d5f0b3a1c7e92468afd0136bd5c7e19a2f4b6d8"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Start every test from a clean slate: no key, no production marker."""
    for name in (
        "SECRET_KEY",
        "GENESIS_ENV",
        "SPACE_ID",
        "RENDER",
        "RAILWAY_ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)


def _as_production(monkeypatch):
    monkeypatch.setenv("SPACE_ID", "genesisno-genesis-automaton")


def test_production_missing_key_refuses_to_start(monkeypatch):
    _as_production(monkeypatch)
    with pytest.raises(RuntimeError):
        appmod._resolve_secret_key()


def test_production_default_key_refuses_to_start(monkeypatch):
    _as_production(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", appmod._DEFAULT_SECRET_KEY)
    with pytest.raises(RuntimeError):
        appmod._resolve_secret_key()


def test_production_short_key_refuses_to_start(monkeypatch):
    _as_production(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError):
        appmod._resolve_secret_key()


def test_genesis_env_production_marker_refuses_to_start(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    with pytest.raises(RuntimeError):
        appmod._resolve_secret_key()


def test_render_marker_refuses_to_start(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError):
        appmod._resolve_secret_key()


def test_production_strong_key_is_used(monkeypatch):
    _as_production(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", STRONG_KEY)
    assert appmod._resolve_secret_key() == STRONG_KEY


def test_dev_missing_key_gets_random_not_default(monkeypatch):
    first = appmod._resolve_secret_key()
    second = appmod._resolve_secret_key()
    assert first and first != appmod._DEFAULT_SECRET_KEY
    assert first != second, "each process must get a fresh random key"


def test_dev_default_key_is_replaced(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", appmod._DEFAULT_SECRET_KEY)
    resolved = appmod._resolve_secret_key()
    assert resolved != appmod._DEFAULT_SECRET_KEY


def test_dev_strong_key_is_used(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", STRONG_KEY)
    assert appmod._resolve_secret_key() == STRONG_KEY


def test_error_message_never_contains_the_key(monkeypatch):
    _as_production(monkeypatch)
    monkeypatch.setenv("SECRET_KEY", appmod._DEFAULT_SECRET_KEY)
    with pytest.raises(RuntimeError) as excinfo:
        appmod._resolve_secret_key()
    assert appmod._DEFAULT_SECRET_KEY not in str(excinfo.value)


def test_known_insecure_keys_are_blocked(monkeypatch):
    _as_production(monkeypatch)
    for weak in ("change-me", "changeme", "secret", "test", "development", "genesis"):
        monkeypatch.setenv("SECRET_KEY", weak)
        with pytest.raises(RuntimeError):
            appmod._resolve_secret_key()


def test_default_key_is_itself_flagged_insecure():
    assert appmod._DEFAULT_SECRET_KEY in appmod._INSECURE_SECRET_KEYS
