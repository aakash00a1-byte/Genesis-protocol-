"""Regressions for scripts/register_telegram_webhook.py.

The Space cannot reach api.telegram.org, so the webhook is registered from
GitHub Actions. These tests drive the real ``main()`` with an injected
``_call`` so no network is used, and pin the properties the fix depends on:

* re-registration is idempotent — a webhook that already points at the Space
  with the wanted updates is left alone (no needless setWebhook);
* a drifted URL or an incomplete ``allowed_updates`` triggers a re-register;
* ``deleteWebhook`` is never called (the Space must never drop the hook);
* a failure is reported with a non-zero exit, never a false success.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "register_telegram_webhook.py"
WEBHOOK_URL = "https://space.invalid/api/telegram/webhook"


def _load():
    spec = importlib.util.spec_from_file_location("register_webhook", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BOT_TOKEN = "123456:SUPERSECRET"
    module.WEBHOOK_URL = WEBHOOK_URL
    return module


def _fake_call(monkeypatch, module, responses, calls):
    """Record each ``_call`` and answer from ``responses`` (method -> result)."""
    state = {"n": 0}

    def _call(method, payload=None):
        calls.append((method, payload))
        result = responses[method]
        if isinstance(result, list):
            value = result[min(state["n"], len(result) - 1)]
            state["n"] += 1
            return value
        return result

    monkeypatch.setattr(module, "_call", _call)


def test_no_token_exits_nonzero_without_calling_telegram(monkeypatch) -> None:
    module = _load()
    module.BOT_TOKEN = ""
    calls: list = []
    _fake_call(monkeypatch, module, {}, calls)
    assert module.main() == 1
    assert calls == []


def test_already_correct_webhook_is_left_alone(monkeypatch) -> None:
    module = _load()
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {
            "getWebhookInfo": {
                "result": {
                    "url": WEBHOOK_URL,
                    "allowed_updates": ["message", "callback_query"],
                }
            }
        },
        calls,
    )
    assert module.main() == 0
    assert [m for m, _ in calls] == ["getWebhookInfo"]


def test_missing_allowed_updates_is_treated_as_correct(monkeypatch) -> None:
    module = _load()
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {"getWebhookInfo": {"result": {"url": WEBHOOK_URL}}},
        calls,
    )
    assert module.main() == 0
    assert [m for m, _ in calls] == ["getWebhookInfo"]


def test_incomplete_allowed_updates_triggers_reregister(monkeypatch) -> None:
    module = _load()
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {
            "getWebhookInfo": [
                {"result": {"url": WEBHOOK_URL, "allowed_updates": ["message"]}},
                {"result": {"url": WEBHOOK_URL}},
            ],
            "setWebhook": {"ok": True},
        },
        calls,
    )
    assert module.main() == 0
    assert [m for m, _ in calls] == ["getWebhookInfo", "setWebhook", "getWebhookInfo"]


def test_drifted_url_reregisters_with_secret(monkeypatch) -> None:
    module = _load()
    module.WEBHOOK_SECRET = "s3cret"
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {
            "getWebhookInfo": [
                {"result": {"url": "https://old.invalid/hook"}},
                {"result": {"url": WEBHOOK_URL}},
            ],
            "setWebhook": {"ok": True},
        },
        calls,
    )
    assert module.main() == 0
    payload = calls[1][1]
    assert payload["url"] == WEBHOOK_URL
    assert payload["secret_token"] == "s3cret"
    assert payload["allowed_updates"] == ["message", "callback_query"]
    assert payload["drop_pending_updates"] is False


def test_never_calls_delete_webhook(monkeypatch) -> None:
    module = _load()
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {
            "getWebhookInfo": [
                {"result": {"url": "https://old.invalid/hook"}},
                {"result": {"url": WEBHOOK_URL}},
            ],
            "setWebhook": {"ok": True},
        },
        calls,
    )
    module.main()
    assert "deleteWebhook" not in [m for m, _ in calls]


def test_rejected_setwebhook_exits_nonzero(monkeypatch) -> None:
    module = _load()
    calls: list = []
    _fake_call(
        monkeypatch,
        module,
        {
            "getWebhookInfo": {"result": {"url": "https://old.invalid/hook"}},
            "setWebhook": {"ok": False, "description": "bad token"},
        },
        calls,
    )
    assert module.main() == 1


def test_unreachable_telegram_exits_nonzero(monkeypatch) -> None:
    module = _load()
    calls: list = []

    def _boom(method, payload=None):
        calls.append(method)
        raise OSError("no route to host")

    monkeypatch.setattr(module, "_call", _boom)
    assert module.main() == 1
    assert calls == ["getWebhookInfo"]
