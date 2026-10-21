#!/usr/bin/env python3
"""Genesis relay + keep-alive loop.

Runs inside a GitHub Actions job (public repo => free, unlimited minutes) and
does three things every tick:

1. Pings the HF Space (a plain GET on the Space root) to reduce the chance it
   sleeps. An HTTP 200 only proves the web layer answered; it is NOT proof the
   bot/worker processes are healthy. We never claim the Space "never sleeps".
2. Relays queued Telegram replies from the Space to Telegram. The Space itself
   cannot reach api.telegram.org (HF free tier blocks that egress), so it parks
   replies in /tmp/telegram_reply_queue.json and this loop delivers them.
3. Once a day, sends a proactive status heartbeat so the admin hears from
   Genesis without having to message it first.

Design notes (from the security review):

* Delivery is idempotent: every reply carries an ``id`` from the queue. Sent
  ids are remembered in ``RELAY_STATE_FILE`` so a failed/partial clear cannot
  re-send the same message on the next tick.
* The queue payload is validated and bounded before anything is sent: a
  malformed entry or an oversized/missing field is dropped, never forwarded.
* Heartbeat text is built from *verified* values only. If the status probe
  fails, the message says so; it never reports a check it did not perform.
* Only the configured admin id ever receives the heartbeat. Nothing is sent to
  a chat id that arrived from the network.

Standard library only. Every outbound secret is read from the environment and
never printed.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import UTC, datetime

HF_SPACE_URL = os.environ.get(
    "HF_SPACE_URL", "https://genesisno-genesis-automaton.hf.space"
).rstrip("/")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()

TICK_SECONDS = int(os.environ.get("RELAY_TICK_SECONDS", "60"))
RUN_SECONDS = int(os.environ.get("RELAY_RUN_SECONDS", str(5 * 3600 + 45 * 60)))
HEARTBEAT_HOURS = float(os.environ.get("RELAY_HEARTBEAT_HOURS", "0") or 0)
STATE_FILE = os.environ.get("RELAY_STATE_FILE", "").strip()
# Optional shared secret; must match TELEGRAM_WEBHOOK_SECRET on the Space.
HF_SHARED_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

# Bounds on anything that arrived from the network.
MAX_REPLY_CHARS = 4000
MAX_QUEUE_ITEMS = 50
MAX_SEEN_IDS = 500
_TG_API = "https://api.telegram.org"


def _log(msg: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}", flush=True)


def _redact(text: str) -> str:
    """Never let a bot token (which lives in the request path) reach a log."""
    if TELEGRAM_BOT_TOKEN:
        text = text.replace(TELEGRAM_BOT_TOKEN, "***")
    return re.sub(r"/bot[^/\s]+", "/bot***", text)


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if HF_SHARED_SECRET:
        headers["X-Telegram-Bot-Api-Secret-Token"] = HF_SHARED_SECRET
    return headers


def _get(url: str, timeout: int = 30) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=_headers())  # noqa: S310
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - relay must never die on one call
        _log(f"GET failed: {type(exc).__name__}")
        return None


def keep_awake() -> bool:
    """Best-effort HTTP ping. True means the Space answered, nothing more."""
    return _get(f"{HF_SPACE_URL}/", timeout=60) is not None


def _load_seen() -> set[str]:
    if not STATE_FILE:
        return set()
    try:
        with open(STATE_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        ids = data.get("sent_ids", [])
        return {str(i) for i in ids} if isinstance(ids, list) else set()
    except Exception:  # noqa: BLE001 - a missing/corrupt state file is not fatal
        return set()


def _save_seen(seen: set[str]) -> None:
    if not STATE_FILE:
        return
    # Keep only the most recent ids so the file stays bounded.
    trimmed = list(seen)[-MAX_SEEN_IDS:]
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as handle:
            json.dump({"sent_ids": trimmed}, handle)
    except Exception as exc:  # noqa: BLE001
        _log(f"state save failed: {type(exc).__name__}")


def _valid_reply(reply: object) -> tuple[str, str, str] | None:
    """Return (id, chat_id, text) for a well-formed entry, else None."""
    if not isinstance(reply, dict):
        return None
    chat_id = reply.get("chat_id")
    text = reply.get("text")
    if not isinstance(chat_id, (str, int)) or not str(chat_id).strip():
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    reply_id = reply.get("id")
    if not isinstance(reply_id, (str, int)) or not str(reply_id).strip():
        # Entries without an id cannot be deduplicated; derive a stable one from
        # the content so a repeated payload is still only sent once per run.
        reply_id = f"{chat_id}:{abs(hash(text))}"
    return str(reply_id), str(chat_id).strip(), text[:MAX_REPLY_CHARS]


def _telegram_send(chat_id: str, text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        _log("cannot send: token or chat id missing")
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"{_TG_API}/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            ok = json.loads(resp.read()).get("ok", False)
        return bool(ok)
    except Exception as exc:  # noqa: BLE001
        _log(f"telegram send failed: {_redact(type(exc).__name__)}")
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
    if not isinstance(queue, dict):
        return 0
    replies = queue.get("replies") or []
    if not isinstance(replies, list) or not replies:
        return 0

    seen = _load_seen()
    sent = 0
    for entry in replies[:MAX_QUEUE_ITEMS]:
        parsed = _valid_reply(entry)
        if parsed is None:
            continue
        reply_id, chat_id, text = parsed
        if reply_id in seen:
            continue
        if _telegram_send(chat_id, text):
            seen.add(reply_id)
            sent += 1

    if sent:
        # Persist first, then clear: if the clear fails we still will not
        # re-send, because the ids are already recorded.
        _save_seen(seen)
        req = urllib.request.Request(
            f"{HF_SPACE_URL}/api/telegram/queue",
            method="DELETE",
            headers=_headers(),
        )
        try:
            urllib.request.urlopen(req, timeout=20).read()  # noqa: S310
        except Exception:  # noqa: BLE001
            pass
    _log(f"relayed {sent}/{len(replies)} queued replies")
    return sent


def heartbeat() -> None:
    """Send one proactive status message to the admin (no message needed from them)."""
    if not TELEGRAM_ADMIN_ID:
        _log("heartbeat skipped: TELEGRAM_ADMIN_ID is not set")
        return

    # Report only what we actually verified. A failed probe is stated as such.
    raw = _get(f"{HF_SPACE_URL}/api/status")
    if raw is None:
        space_line = "unreachable (status probe failed)"
    else:
        try:
            payload = json.loads(raw)
            reported = payload.get("status") if isinstance(payload, dict) else None
            space_line = str(reported) if reported else "answered (no status field)"
        except ValueError:
            space_line = "answered (non-JSON status)"

    text = (
        "🧬 Genesis heartbeat\n"
        f"HF Space: {space_line}\n"
        f"Time (UTC): {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}\n"
        "Relay is running. (An HTTP answer is not a health check of the bot.)"
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
    next_heartbeat = (
        started + HEARTBEAT_HOURS * 3600.0 if HEARTBEAT_HOURS > 0 else float("inf")
    )
    while time.monotonic() - started < RUN_SECONDS:
        keep_awake()
        relay_once()
        if time.monotonic() >= next_heartbeat:
            heartbeat()
            next_heartbeat = time.monotonic() + HEARTBEAT_HOURS * 3600.0
        time.sleep(TICK_SECONDS)
    _log("relay loop finished; the next scheduled run takes over")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "heartbeat":
        heartbeat()
        sys.exit(0)
    sys.exit(main())
