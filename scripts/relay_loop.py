#!/usr/bin/env python3
# Genesis relay + keep-alive loop: pings the HF Space, delivers queued Telegram replies, and sends the daily heartbeat.
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

import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime

HF_SPACE_URL = os.environ.get(
    "HF_SPACE_URL", "https://genesisno-genesis-automaton.hf.space"
).rstrip("/")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID", "").strip()
# Where the news digest is delivered. Defaults to the admin DM; set
# TELEGRAM_NEWS_CHAT_ID to a channel id (e.g. -1001234567890) to post there.
NEWS_CHAT_ID = os.environ.get("TELEGRAM_NEWS_CHAT_ID", "").strip() or TELEGRAM_ADMIN_ID

TICK_SECONDS = int(os.environ.get("RELAY_TICK_SECONDS", "60"))
RUN_SECONDS = int(os.environ.get("RELAY_RUN_SECONDS", str(5 * 3600 + 45 * 60)))
HEARTBEAT_HOURS = float(os.environ.get("RELAY_HEARTBEAT_HOURS", "0") or 0)
STATE_FILE = os.environ.get("RELAY_STATE_FILE", "").strip()

# News digest: a recurring tech/sports/markets roundup pushed to the admin.
NEWS_ENABLED = os.environ.get("NEWS_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
    "",
}
NEWS_INTERVAL_SECONDS = int(os.environ.get("NEWS_INTERVAL_SECONDS", "300"))
NEWS_MAX_PER_CATEGORY = int(os.environ.get("NEWS_MAX_PER_CATEGORY", "3"))
# Send each category as its own message (1) or one combined digest (0).
NEWS_SEPARATE_MESSAGES = os.environ.get(
    "NEWS_SEPARATE_MESSAGES", "1"
).strip().lower() not in {"0", "false", "no", "off", ""}
# Pause between category messages so they arrive as separate, ordered messages.
NEWS_SEND_GAP_SECONDS = float(os.environ.get("NEWS_SEND_GAP_SECONDS", "1.5"))
# A live market ticker (indices, commodities, crypto, FX) sent as its own message.
MARKET_ENABLED = os.environ.get("MARKET_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
    "",
}
# (label, yahoo symbol) — Yahoo Finance chart API returns price + previous close.
MARKET_SYMBOLS: list[tuple[str, str]] = [
    ("Nifty 50", "^NSEI"),
    ("Sensex", "^BSESN"),
    ("S&P 500", "^GSPC"),
    ("Nasdaq", "^IXIC"),
    ("Dow Jones", "^DJI"),
    ("Gold", "GC=F"),
    ("Silver", "SI=F"),
    ("Crude Oil", "CL=F"),
    ("USD/INR", "INR=X"),
    ("Bitcoin", "BTC-USD"),
    ("Ethereum", "ETH-USD"),
]
# Have the Space AI write a short Hinglish briefing from the headlines + market.
AGENT_BRIEFING_ENABLED = os.environ.get("AGENT_BRIEFING_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
    "",
}
# Weather: a short forecast for one city, via the free Open-Meteo API (no key).
WEATHER_ENABLED = os.environ.get("WEATHER_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
    "",
}
WEATHER_CITY = os.environ.get("WEATHER_CITY", "Delhi").strip() or "Delhi"
# (label, latitude, longitude) — one city keeps it simple; extend if needed.
WEATHER_PLACES: list[tuple[str, float, float]] = [
    ("Delhi", 28.6139, 77.2090),
    ("Mumbai", 19.0760, 72.8777),
    ("Kolkata", 22.5726, 88.3639),
    ("Chennai", 13.0827, 80.2707),
]
# WMO weather interpretation codes -> short text.
WMO_CODES: dict[int, str] = {
    0: "Clear",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Violent showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm + hail",
    99: "Thunderstorm + hail",
}
NEWS_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "🌍 WORLD": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
    ],
    "🇮🇳 INDIA": [
        ("NDTV", "https://feeds.feedburner.com/ndtvnews-top-stories"),
        ("The Hindu", "https://www.thehindu.com/news/national/feeder/default.rss"),
    ],
    "💻 TECH": [
        ("BBC Tech", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "⚽ SPORTS": [
        ("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
        ("Sky Sports", "https://www.skysports.com/rss/12040"),
    ],
    "📈 MARKETS": [
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ],
    "🪙 CRYPTO": [
        ("Cointelegraph", "https://cointelegraph.com/rss"),
    ],
    "🪦 OBITUARIES": [
        ("The Guardian", "https://www.theguardian.com/tone/obituaries/rss"),
        ("NYT", "https://rss.nytimes.com/services/xml/rss/nyt/Obituaries.xml"),
    ],
}
# Cap how much of any feed we read/parse, so a hostile or huge feed cannot
# exhaust memory.
MAX_FEED_BYTES = 512 * 1024
# Telegram sendMessage rejects text over 4096 chars.
MAX_DIGEST_CHARS = 3900
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


def _reason(exc: BaseException) -> str:
    """A redacted, actionable one-line reason for a failed HTTP call.

    ``type(exc).__name__`` alone hides why a call failed; an HTTP error's
    status code (429, 404, 500...) is what tells an operator whether to wait,
    fix a URL, or redeploy.
    """
    code = getattr(exc, "code", None)
    detail = f"{type(exc).__name__} (HTTP {code})" if code else type(exc).__name__
    return _redact(detail)


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
        _log(f"GET {_redact(url)} failed: {_reason(exc)}")
        return None


def _post(url: str, payload: dict, timeout: int = 60) -> bytes | None:
    try:
        req = urllib.request.Request(  # noqa: S310
            url,
            data=json.dumps(payload).encode(),
            headers={**_headers(), "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read()
    except Exception as exc:  # noqa: BLE001 - relay must never die on one call
        _log(f"POST {_redact(url)} failed: {_reason(exc)}")
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
        _log(f"telegram send failed: {_reason(exc)}")
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
        except Exception as exc:  # noqa: BLE001 - ids are persisted, so no re-send
            # Not fatal (delivery is idempotent), but a queue that never clears
            # is re-fetched every tick, so say why instead of hiding it.
            _log(f"queue clear failed: {_reason(exc)}")
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


_ATOM = "{http://www.w3.org/2005/Atom}"


def _clean(text: str | None) -> str:
    """Collapse whitespace and unescape HTML entities from feed text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _fetch_feed_titles(url: str) -> list[str]:
    """Return up to NEWS_MAX_PER_CATEGORY headlines from an RSS/Atom feed."""
    try:
        req = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "GenesisNews/1.0 (+relay)"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = resp.read(MAX_FEED_BYTES)
    except Exception as exc:  # noqa: BLE001 - one dead feed must not stop the rest
        _log(f"feed failed ({url.split('/')[2]}): {type(exc).__name__}")
        return []
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return []
    items = root.findall(".//item") or root.findall(f".//{_ATOM}entry")
    titles: list[str] = []
    for item in items:
        node = item.find("title")
        if node is None:
            node = item.find(f"{_ATOM}title")
        title = _clean(node.text if node is not None else "")
        if title:
            titles.append(title)
        if len(titles) >= NEWS_MAX_PER_CATEGORY:
            break
    return titles


def build_news_sections() -> list[str]:
    """Build one message body per category, skipping empty categories."""
    sections: list[str] = []
    seen_titles: set[str] = set()
    for label, feeds in NEWS_CATEGORIES.items():
        lines: list[str] = []
        for source, url in feeds:
            for title in _fetch_feed_titles(url):
                key = title.lower()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                lines.append(f"• {title} — {source}")
                if len(lines) >= NEWS_MAX_PER_CATEGORY:
                    break
            if len(lines) >= NEWS_MAX_PER_CATEGORY:
                break
        if lines:
            sections.append(label + "\n" + "\n".join(lines))
    return sections


def collect_headlines(limit: int = 30) -> list[str]:
    """Collect deduplicated headlines across all feeds for the AI briefing."""
    headlines: list[str] = []
    seen: set[str] = set()
    for _label, feeds in NEWS_CATEGORIES.items():
        for source, url in feeds:
            for title in _fetch_feed_titles(url):
                key = title.lower()
                if key in seen:
                    continue
                seen.add(key)
                headlines.append(f"{title} ({source})")
                if len(headlines) >= limit:
                    return headlines
    return headlines


def collect_market_lines() -> list[str]:
    """Collect 'label: price (+x%)' lines for the AI briefing."""
    lines: list[str] = []
    for label, symbol in MARKET_SYMBOLS:
        quote = _fetch_quote(symbol)
        if quote is None:
            continue
        price, prev = quote
        if prev == 0:
            continue
        pct = (price - prev) / prev * 100.0
        sign = "+" if pct >= 0 else ""
        lines.append(f"{label}: {_fmt_number(price)} ({sign}{pct:.2f}%)")
    return lines


def _fit(text: str) -> str:
    """Trim to stay under Telegram's 4096-char limit."""
    if len(text) > MAX_DIGEST_CHARS:
        text = text[: MAX_DIGEST_CHARS - 20].rstrip() + "\n\n…(trimmed)"
    return text


def build_news_digest() -> str | None:
    """Build one combined tech/sports/markets digest, or None if all feeds failed."""
    sections = build_news_sections()
    if not sections:
        return None
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return _fit("📰 Genesis news update\n" + "\n\n".join(sections) + f"\n\n🕒 {stamp}")


def _send_report(label: str, build: Callable[[], str | None], reason: str, ok: str) -> None:
    """Guard on the chat id, build the body, send it, and log the outcome.

    Every recurring report (news, market, weather) has this shape; ``build``
    returns None when there is nothing worth sending.
    """
    if not NEWS_CHAT_ID:
        _log(f"{label} skipped: no news chat id is set")
        return
    text = build()
    if text is None:
        _log(f"{label} skipped: {reason}")
        return
    if _telegram_send(NEWS_CHAT_ID, text):
        _log(ok)


def news_digest() -> None:
    """Send the news digest to the news chat (admin DM by default).

    By default each category goes as its own message, sent one after another, so
    the admin gets them one at a time instead of a single wall of text.
    """
    if not NEWS_CHAT_ID:
        _log("news skipped: no news chat id is set")
        return

    if NEWS_SEPARATE_MESSAGES:
        sections = build_news_sections()
        if not sections:
            _log("news skipped: no feed returned headlines")
            return
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        total = len(sections)
        sent = 0
        for index, section in enumerate(sections, 1):
            header = f"📰 Genesis news ({index}/{total})\n\n"
            footer = f"\n\n🕒 {stamp}" if index == total else ""
            if _telegram_send(NEWS_CHAT_ID, _fit(header + section + footer)):
                sent += 1
                if index < total and NEWS_SEND_GAP_SECONDS > 0:
                    time.sleep(NEWS_SEND_GAP_SECONDS)
        _log(f"news sent {sent}/{total} category messages")
        return

    text = build_news_digest()
    if text is None:
        _log("news skipped: no feed returned headlines")
        return
    if _telegram_send(NEWS_CHAT_ID, text):
        _log("news digest sent")


def _fmt_number(value: float) -> str:
    """Format a price with thousands separators, trimming needless decimals."""
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:,.4f}"


def _fetch_quote(symbol: str) -> tuple[float, float] | None:
    """Return (price, previous_close) for a Yahoo symbol, or None on failure."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{urllib.parse.quote(symbol)}?interval=1d&range=1d"
    )
    try:
        req = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "Mozilla/5.0 GenesisNews/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read(MAX_FEED_BYTES))
    except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the rest
        _log(f"quote failed ({symbol}): {type(exc).__name__}")
        return None
    try:
        meta = data["chart"]["result"][0]["meta"]
        price = float(meta["regularMarketPrice"])
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if prev is None:
            return None
        return price, float(prev)
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def build_market_report() -> str | None:
    """Build a live market ticker, or None if no symbol returned a price."""
    lines: list[str] = []
    movers: list[tuple[float, str]] = []
    for label, symbol in MARKET_SYMBOLS:
        quote = _fetch_quote(symbol)
        if quote is None:
            continue
        price, prev = quote
        if prev == 0:
            continue
        change = price - prev
        pct = change / prev * 100.0
        arrow = "🟢" if change >= 0 else "🔴"
        sign = "+" if change >= 0 else ""
        lines.append(
            f"{arrow} {label}: {_fmt_number(price)} "
            f"({sign}{pct:.2f}%)"
        )
        movers.append((pct, label))
    if not lines:
        return None
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    report = "📊 Genesis market update\n\n" + "\n".join(lines)
    if len(movers) >= 2:
        movers.sort()
        worst, best = movers[0], movers[-1]
        # Label by the sign of the move: on a day when everything falls, the
        # "best" mover is still a loss, so it must not be called a gainer (and
        # vice versa for the weakest mover on an all-green day).
        best_head = "🏆 Top gainer" if best[0] >= 0 else "🟢 Best performer"
        worst_head = "📉 Top loser" if worst[0] < 0 else "🔴 Weakest"
        report += (
            f"\n\n{best_head}: {best[1]} ({best[0]:+.2f}%)"
            f"\n{worst_head}: {worst[1]} ({worst[0]:+.2f}%)"
        )
    return report + f"\n\n🕒 {stamp}"


def market_report() -> None:
    """Send the live market ticker to the news chat."""
    _send_report(
        "market", build_market_report, "no quote returned a price", "market report sent"
    )


def _fetch_weather(lat: float, lon: float) -> dict | None:
    """Return today's min/max, current temp and condition, or None on failure."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=auto&forecast_days=1"
    )
    try:
        req = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": "Mozilla/5.0 GenesisNews/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
            data = json.loads(resp.read(MAX_FEED_BYTES))
    except Exception as exc:  # noqa: BLE001 - weather must never stop the relay
        _log(f"weather failed: {type(exc).__name__}")
        return None
    try:
        current = data["current"]
        daily = data["daily"]
        return {
            "temp": float(current["temperature_2m"]),
            "code": int(current["weather_code"]),
            "tmax": float(daily["temperature_2m_max"][0]),
            "tmin": float(daily["temperature_2m_min"][0]),
            "rain": daily.get("precipitation_probability_max", [None])[0],
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def build_weather_report() -> str | None:
    """Build a short weather message for the configured cities."""
    lines: list[str] = []
    for label, lat, lon in WEATHER_PLACES:
        if WEATHER_CITY.lower() not in ("", "all") and label.lower() != WEATHER_CITY.lower():
            continue
        w = _fetch_weather(lat, lon)
        if w is None:
            continue
        condition = WMO_CODES.get(w["code"], f"Code {w['code']}")
        line = (
            f"🌤 {label}: {condition}, {w['temp']:.0f}°C"
            f" (min {w['tmin']:.0f}° / max {w['tmax']:.0f}°)"
        )
        if isinstance(w["rain"], (int, float)):
            line += f", rain {w['rain']:.0f}%"
        lines.append(line)
    if not lines:
        return None
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return "🌦 Genesis weather\n\n" + "\n".join(lines) + f"\n\n🕒 {stamp}"


def weather_report() -> None:
    """Send the weather to the news chat."""
    _send_report(
        "weather", build_weather_report, "no city returned data", "weather report sent"
    )


def agent_briefing() -> None:
    """Ask the Space AI to write a briefing, then deliver it to the news chat.

    This gives the agent a real job: it reads the day's headlines and market
    numbers and writes its own Hinglish summary, which the relay posts.
    """
    if not NEWS_CHAT_ID:
        _log("briefing skipped: no news chat id is set")
        return
    headlines = collect_headlines()
    market_lines = collect_market_lines()
    if not headlines and not market_lines:
        _log("briefing skipped: no data collected")
        return
    raw = _post(
        f"{HF_SPACE_URL}/api/briefing",
        {"headlines": headlines, "market": market_lines},
        timeout=90,
    )
    if raw is None:
        _log("briefing skipped: the Space did not answer")
        return
    try:
        data = json.loads(raw)
    except ValueError:
        _log("briefing skipped: the Space sent non-JSON")
        return
    briefing = data.get("briefing") if isinstance(data, dict) else None
    if not isinstance(briefing, str) or not briefing.strip():
        _log("briefing skipped: the AI returned no text")
        return
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    text = f"🧠 Genesis AI briefing\n\n{briefing.strip()}\n\n🕒 {stamp}"
    if _telegram_send(NEWS_CHAT_ID, _fit(text)):
        _log("agent briefing sent")


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
    # Send the first news digest immediately, then every NEWS_INTERVAL_SECONDS.
    next_news = started if NEWS_ENABLED and NEWS_INTERVAL_SECONDS > 0 else float("inf")
    # Market ticker follows the news, offset so the two do not collide.
    next_market = (
        started + 5.0 if MARKET_ENABLED and NEWS_INTERVAL_SECONDS > 0 else float("inf")
    )
    # The AI briefing follows the market, offset again.
    next_briefing = (
        started + 10.0
        if AGENT_BRIEFING_ENABLED and NEWS_INTERVAL_SECONDS > 0
        else float("inf")
    )
    # Weather follows the briefing.
    next_weather = (
        started + 15.0
        if WEATHER_ENABLED and NEWS_INTERVAL_SECONDS > 0
        else float("inf")
    )
    while time.monotonic() - started < RUN_SECONDS:
        keep_awake()
        relay_once()
        if time.monotonic() >= next_heartbeat:
            heartbeat()
            next_heartbeat = time.monotonic() + HEARTBEAT_HOURS * 3600.0
        if time.monotonic() >= next_news:
            news_digest()
            next_news = time.monotonic() + NEWS_INTERVAL_SECONDS
        if time.monotonic() >= next_market:
            market_report()
            next_market = time.monotonic() + NEWS_INTERVAL_SECONDS
        if time.monotonic() >= next_briefing:
            agent_briefing()
            next_briefing = time.monotonic() + NEWS_INTERVAL_SECONDS
        if time.monotonic() >= next_weather:
            weather_report()
            next_weather = time.monotonic() + NEWS_INTERVAL_SECONDS
        time.sleep(TICK_SECONDS)
    _log("relay loop finished; the next scheduled run takes over")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "heartbeat":
        heartbeat()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "news":
        news_digest()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "market":
        market_report()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "briefing":
        agent_briefing()
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "weather":
        weather_report()
        sys.exit(0)
    sys.exit(main())
