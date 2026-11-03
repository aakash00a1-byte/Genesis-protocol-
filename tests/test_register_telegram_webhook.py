"""Regressions for the Telegram webhook registration script.

Pinned defect: a webhook whose URL already matched the Space was treated as
"already correct" and the script returned early *without* re-registering
``setWebhook``. Telegram never reports ``secret_token`` back from
``getWebhookInfo``, so a webhook that had been set without the shared secret
kept 401-ing every update — the exact way live Telegram delivery broke. When a
secret is configured the script must now always re-register.

The script is driven through an injected ``_call`` layer, so no network request
and no real secret is ever used.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "register_telegram_webhook.py"
)

SECRET = "s3cret-value"
TOKEN = "123456:FAKE-TOKEN"
SPACE_URL = "https://space.invalid"


def _load(monkeypatch, **env):
    for key in ("TELEGRAM_BOT_TOKEN", "SPACE_URL", "TELEGRAM_WEBHOOK_SECRET"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("register_webhook_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["register_webhook_test"] = module
    spec.loader.exec_module(module)
    return module


class _FakeTelegram:
    """Records every ``_call`` and answers from canned Telegram responses."""

    def __init__(self, *, info, set_result=None, set_raises=None, verify_info=None):
        self.calls: list[tuple[str, dict | None]] = []
        self._info = info
        self._set_result = set_result
        self._set_raises = set_raises
        self._verify_info = verify_info
        self._info_served = 0

    def __call__(self, method, payload=None):
        self.calls.append((method, payload))
        if method == "getWebhookInfo":
            self._info_served += 1
            # First getWebhookInfo = current state; later = post-set verify.
            if self._info_served > 1 and self._verify_info is not None:
                return self._verify_info
            return self._info
        if method == "setWebhook":
            if self._set_raises is not None:
                raise self._set_raises
            return self._set_result if self._set_result is not None else {"ok": True}
        raise AssertionError(f"unexpected method {method}")

    def setwebhook_payloads(self):
        return [p for m, p in self.calls if m == "setWebhook"]

    def setwebhook_called(self) -> bool:
        return any(m == "setWebhook" for m, _ in self.calls)


def _matching_info(updates=("message", "callback_query")):
    return {"ok": True, "result": {"url": f"{SPACE_URL}/api/telegram/webhook",
                                   "allowed_updates": list(updates)}}


def test_matching_url_with_secret_forces_reregistration(monkeypatch, capsys):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET=SECRET,
    )
    fake = _FakeTelegram(info=_matching_info(), verify_info=_matching_info())
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 0
    assert fake.setwebhook_called(), "matching URL + configured secret must re-register"
    payload = fake.setwebhook_payloads()[0]
    assert payload["secret_token"] == SECRET
    assert payload["url"] == f"{SPACE_URL}/api/telegram/webhook"


def test_matching_url_without_secret_is_noop(monkeypatch):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET="",
    )
    fake = _FakeTelegram(info=_matching_info())
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 0
    assert not fake.setwebhook_called(), "no secret configured -> a match is a safe no-op"


def test_allowed_updates_are_enforced(monkeypatch):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET="",
    )
    # Current webhook is missing callback_query -> must be repaired.
    fake = _FakeTelegram(
        info=_matching_info(updates=("message",)),
        verify_info=_matching_info(),
    )
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 0
    payload = fake.setwebhook_payloads()[0]
    assert payload["allowed_updates"] == ["message", "callback_query"]
    assert payload["max_connections"] == 5
    assert payload["drop_pending_updates"] is False


def test_drifted_url_registers_without_secret_when_unset(monkeypatch):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET="",
    )
    fake = _FakeTelegram(
        info={"ok": True, "result": {"url": "https://old.invalid/hook"}},
        verify_info=_matching_info(),
    )
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 0
    payload = fake.setwebhook_payloads()[0]
    assert "secret_token" not in payload


def test_secret_is_sent_but_never_printed(monkeypatch, capsys):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET=SECRET,
    )
    fake = _FakeTelegram(info=_matching_info(), verify_info=_matching_info())
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 0
    out = capsys.readouterr().out
    assert SECRET not in out, "the shared secret must never be logged"
    assert TOKEN not in out, "the bot token must never be logged"


def test_failed_registration_returns_nonzero(monkeypatch):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET=SECRET,
    )
    fake = _FakeTelegram(
        info=_matching_info(),
        set_result={"ok": False, "description": "Bad Request: bad webhook"},
    )
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 1


def test_verify_mismatch_returns_nonzero(monkeypatch):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET=SECRET,
    )
    fake = _FakeTelegram(
        info=_matching_info(),
        verify_info={"ok": True, "result": {"url": "https://wrong.invalid/hook"}},
    )
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 1


def test_getwebhookinfo_error_returns_nonzero_and_redacts(monkeypatch, capsys):
    mod = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=TOKEN,
        SPACE_URL=SPACE_URL,
        TELEGRAM_WEBHOOK_SECRET=SECRET,
    )

    def boom(method, payload=None):
        raise RuntimeError(f"connection to /bot{TOKEN}/getWebhookInfo failed")

    monkeypatch.setattr(mod, "_call", boom)

    assert mod.main() == 1
    out = capsys.readouterr().out
    assert TOKEN not in out
    assert "/bot***" in out


def test_missing_token_returns_nonzero(monkeypatch):
    mod = _load(monkeypatch, TELEGRAM_BOT_TOKEN="", SPACE_URL=SPACE_URL)
    fake = _FakeTelegram(info=_matching_info())
    monkeypatch.setattr(mod, "_call", fake)

    assert mod.main() == 1
    assert not fake.setwebhook_called()
