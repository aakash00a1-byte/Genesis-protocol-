#!/usr/bin/env python3
"""Genesis relay + keep-alive loop.

Runs inside a GitHub Actions job (public repo => free, unlimited minutes) and
does three things every tick:

1. Keeps the HF Space awake (a plain GET on the Space root), so it never sleeps.
2. Relays queued Telegram replies from the Space to Telegram. The Space itself
   cannot reach api.telegram.org (HF free tier blocks that egress), so it parks
   replies in /tmp/telegram_reply_queue.json and this loop delivers them.
3. Once a day, sends a proactive status heartbeat so the admin hears from
   Genesis without having to message it first.

Standard library only. Every outbound secret is read from the environment and
never printed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HF_SPACE_URL = os.environ.get(
    "HF_SPACE_URL", "https://genesisno-genesis-automaton.hf.space"
).rstrip("/")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()

TICK_SECONDS = int(os.environ.get("RELAY_TICK_SECONDS", "60"))
RUN_SECONDS = int(os.environ.get("RELAY_RUN_SECONDS", str(5 * 3600 + 45 * 60)))


def _log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def _get(url: str, timeout: int = 30) -> bytes | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - relay must never die on one call
        _log(f"GET failed: {type(exc).__name__}")
        return None


def keep_awake() -> bool:
    return _get(f"{HF_SPACE_URL}/", timeout=60) is not None


def _telegram_send(chat_id: str, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        _log("cannot send: token or chat id missing")
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            ok = json.loads(resp.read()).get("ok", False)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        _log(f"telegram send failed: {type(exc).__name__}")
        return False


def relay_once() -> int:
    """Deliver every queued reply. Returns how many were sent."""
    raw = _get(f"{HF_SPACE_URL}/api/telegram/queue")
    if raw is None:
        return 0
    try:
        queue = json.loads(raw)
    except ValueError:
        return 0
    replies = queue.get("replies") or []
    if not replies:
        return 0

    sent = 0
    for reply in replies:
        if _telegram_send(str(reply.get("chat_id", "")), str(reply.get("text", ""))):
            sent += 1

    # Clear only after a delivery attempt so a failed send is retried next tick.
    if sent:
        req = urllib.request.Request(
            f"{HF_SPACE_URL}/api/telegram/queue", method="DELETE"
        )
        try:
            urllib.request.urlopen(req, timeout=20).read()
        except Exception:  # noqa: BLE001
            pass
    _log(f"relayed {sent}/{len(replies)} queued replies")
    return sent


def heartbeat() -> None:
    """Send one proactive status message to the admin (no message needed from them)."""
    if not TELEGRAM_ADMIN_ID:
        _log("heartbeat skipped: TELEGRAM_ADMIN_ID is not set")
        return
    status = _get(f"{HF_SPACE_URL}/api/status")
    state = "reachable"
    if status is not None:
        try:
            state = json.loads(status).get("status", "ok")
        except ValueError:
            pass
    text = (
        "🧬 Genesis heartbeat\n"
        f"HF Space: {state}\n"
        f"Time (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n"
        "Relay + keep-alive are running."
    )
    if _telegram_send(TELEGRAM_ADMIN_ID, text):
        _log("heartbeat sent")


def main() -> int:
    if not TELEGRAM_BOT_TOKEN:
        _log("TELEGRAM_BOT_TOKEN is not set; relay cannot deliver replies")
    _log(
        f"relay loop start: tick={TICK_SECONDS}s run={RUN_SECONDS}s "
        f"space={HF_SPACE_URL}"
    )
    started = time.monotonic()
    while time.monotonic() - started < RUN_SECONDS:
        keep_awake()
        relay_once()
        time.sleep(TICK_SECONDS)
    _log("relay loop finished; the next scheduled run takes over")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "heartbeat":
        heartbeat()
        sys.exit(0)
    sys.exit(main())
