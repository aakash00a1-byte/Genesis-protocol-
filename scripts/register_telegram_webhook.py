#!/usr/bin/env python3
"""Register the Telegram webhook from a host that can reach api.telegram.org.

The HF Space cannot: Hugging Face's free tier blocks egress to
api.telegram.org, so its own ``setWebhook`` call times out and the webhook is
never registered. GitHub Actions *can* reach Telegram, so this runs there
(from the keep-alive relay workflow) and re-registers the webhook on every run.

It is idempotent and self-healing: it reads the current webhook first, sets it
only when the URL has drifted or Telegram reports a problem, then verifies.

Env:
  TELEGRAM_BOT_TOKEN        required
  SPACE_URL                 default https://genesisno-genesis-automaton.hf.space
  TELEGRAM_WEBHOOK_SECRET   optional; sent as Telegram's secret_token
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
SPACE_URL = os.environ.get(
    "SPACE_URL", "https://genesisno-genesis-automaton.hf.space"
).rstrip("/")
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
WEBHOOK_URL = f"{SPACE_URL}/api/telegram/webhook"


def _call(method: str, payload: dict | None = None) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(  # noqa: S310 - fixed Telegram host
        url,
        data=data,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read() or b"{}")


def _is_healthy(result: dict) -> bool:
    """Return True only when Telegram is not reporting a delivery failure.

    A webhook whose URL matches but whose ``last_error_message`` is set is NOT
    healthy: the endpoint is rejecting every update. That is exactly the state
    a stale ``setWebhook`` leaves behind when the Space later starts enforcing
    ``TELEGRAM_WEBHOOK_SECRET`` but Telegram was never told the secret. Treating
    a matching URL as "already correct" made this script a no-op forever, so
    the failure never healed.
    """
    return not result.get("last_error_message")


def main() -> int:
    if not BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN is not set; skipping webhook registration")
        return 1

    try:
        info = _call("getWebhookInfo")
    except Exception as exc:  # noqa: BLE001
        print(f"getWebhookInfo failed: {type(exc).__name__}: {exc}")
        return 1

    result = info.get("result") or {}
    current = result.get("url", "")
    want_updates = ["message", "callback_query"]
    current_updates = result.get("allowed_updates")
    last_error = result.get("last_error_message", "")

    print(f"current webhook: {current or '(none)'}")
    print(f"last_error: {last_error or '(none)'}")
    print(f"secret configured: {bool(WEBHOOK_SECRET)}")

    if (
        current == WEBHOOK_URL
        and (not current_updates or set(want_updates) <= set(current_updates))
        and _is_healthy(result)
    ):
        print("webhook already correct and healthy; nothing to do")
        return 0

    payload: dict = {
        "url": WEBHOOK_URL,
        "max_connections": 5,
        "allowed_updates": want_updates,
        "drop_pending_updates": False,
    }
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    else:
        # The Space enforces the secret when TELEGRAM_WEBHOOK_SECRET is set
        # there. Without the matching repo secret we cannot present it, so a
        # re-registration would just re-create the same 401. Fail loudly
        # instead of pushing a webhook we know the Space will reject.
        print(
            "TELEGRAM_WEBHOOK_SECRET is not set as a repo secret. If the Space "
            "enforces it, the webhook will keep returning 401 UNAUTHORIZED. "
            "Set the repo secret to the same value as the Space, then re-run."
        )

    try:
        result = _call("setWebhook", payload)
    except Exception as exc:  # noqa: BLE001
        print(f"setWebhook failed: {type(exc).__name__}: {exc}")
        return 1

    if not result.get("ok"):
        print(f"setWebhook rejected: {result.get('description')}")
        return 1

    verify = _call("getWebhookInfo")
    vr = verify.get("result") or {}
    url_now = vr.get("url", "")
    verify_error = vr.get("last_error_message", "")
    print(f"webhook set -> {url_now}")
    if verify_error:
        print(f"WARNING: Telegram still reports: {verify_error}")
        return 1
    return 0 if url_now == WEBHOOK_URL else 1


if __name__ == "__main__":
    sys.exit(main())
