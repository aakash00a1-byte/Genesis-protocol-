"""Regressions for the Telegram webhook registration script.

The script runs from GitHub Actions (HF free tier cannot reach api.telegram.org).
It is probed with an injected ``_call``, so no network call is made. Pinned
defects:

* a webhook whose URL matches but whose ``last_error_message`` is set must be
  treated as broken and re-registered, not reported as "already correct". That
  early return is what let a 401 loop persist for days;
* when the repo secret is absent but the Space enforces it, the script must say
  so instead of silently re-creating the same 401;
* ``drop_pending_updates`` stays False so a heal never discards user messages.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "register_telegram_webhook.py"
)
WEBHOOK_URL = "https://genesisno-genesis-automaton.hf.space/api/telegram/webhook"


def _load(monkeypatch, **env):
    for key in ("TELEGRAM_BOT_TOKEN", "SPACE_URL", "TELEGRAM_WEBHOOK_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("register_webhook_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["register_webhook_test"] = module
    spec.loader.exec_module(module)
    return module


class _Recorder:
    """Stands in for ``_call``; records setWebhook payloads."""

    def __init__(self, info, setwebhook_ok=True):
        self.info = info
        self.setwebhook_ok = setwebhook_ok
        self.calls = []

    def __call__(self, method, payload=None):
        self.calls.append((method, payload))
        if method == "getWebhookInfo":
            return {"ok": True, "result": self.info}
        if method == "setWebhook":
            if not self.setwebhook_ok:
                return {"ok": False, "description": "rejected"}
            self.info = {
                "url": WEBHOOK_URL,
                "allowed_updates": ["message", "callback_query"],
            }
            return {"ok": True}
        raise AssertionError(f"unexpected method {method}")


def test_matching_url_with_error_is_reregistered(monkeypatch):
    """A matching URL plus last_error must not short-circuit as healthy."""
    module = _load(monkeypatch, TELEGRAM_WEBHOOK_SECRET="s3cret")
    recorder = _Recorder(
        {
            "url": WEBHOOK_URL,
            "allowed_updates": ["message", "callback_query"],
            "last_error_message": "Wrong response from the webhook: 401 UNAUTHORIZED",
        }
    )
    monkeypatch.setattr(module, "_call", recorder)

    assert module.main() == 0
    methods = [m for m, _ in recorder.calls]
    assert "setWebhook" in methods, "must re-register when Telegram reports an error"


def test_healthy_webhook_is_left_alone(monkeypatch):
    """No error and a matching URL -> no setWebhook call."""
    module = _load(monkeypatch, TELEGRAM_WEBHOOK_SECRET="s3cret")
    recorder = _Recorder(
        {
            "url": WEBHOOK_URL,
            "allowed_updates": ["message", "callback_query"],
        }
    )
    monkeypatch.setattr(module, "_call", recorder)

    assert module.main() == 0
    assert [m for m, _ in recorder.calls] == ["getWebhookInfo"]


def test_secret_is_sent_and_pending_updates_kept(monkeypatch):
    """The secret travels as secret_token; pending updates are never dropped."""
    module = _load(monkeypatch, TELEGRAM_WEBHOOK_SECRET="s3cret")
    recorder = _Recorder({"url": ""})
    monkeypatch.setattr(module, "_call", recorder)

    module.main()
    payload = next(p for m, p in recorder.calls if m == "setWebhook")
    assert payload["secret_token"] == "s3cret"
    assert payload["drop_pending_updates"] is False


def test_missing_secret_warns(monkeypatch, capsys):
    """Without the repo secret the script must explain the likely 401."""
    module = _load(monkeypatch)
    recorder = _Recorder({"url": ""})
    monkeypatch.setattr(module, "_call", recorder)

    module.main()
    out = capsys.readouterr().out
    assert "TELEGRAM_WEBHOOK_SECRET is not set" in out
    payload = next(p for m, p in recorder.calls if m == "setWebhook")
    assert "secret_token" not in payload


def test_persistent_error_after_set_fails(monkeypatch):
    """If Telegram still reports an error after setWebhook, exit non-zero."""
    module = _load(monkeypatch, TELEGRAM_WEBHOOK_SECRET="s3cret")

    class _StillBroken(_Recorder):
        def __call__(self, method, payload=None):
            self.calls.append((method, payload))
            if method == "getWebhookInfo":
                return {
                    "ok": True,
                    "result": {
                        "url": WEBHOOK_URL,
                        "last_error_message": "401 UNAUTHORIZED",
                    },
                }
            return {"ok": True}

    recorder = _StillBroken({})
    monkeypatch.setattr(module, "_call", recorder)
    assert module.main() == 1
