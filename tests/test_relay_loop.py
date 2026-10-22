"""Regressions for the Telegram relay + heartbeat worker (scripts/relay_loop.py).

The worker is probed with an injected HTTP layer and a fake Telegram sender, so
no network call and no real message is made. Pinned defects:

* a reply entry with no/invalid chat_id or text is dropped, never forwarded;
* delivery is idempotent — the same id is not sent twice across ticks;
* the token never appears in a logged transport error;
* the heartbeat reports an unreachable probe honestly instead of inventing a
  "reachable" status.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

RELAY_PATH = Path(__file__).resolve().parent.parent / "scripts" / "relay_loop.py"


def _load(monkeypatch, **env):
    for key in (
        "HF_SPACE_URL",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_ADMIN_ID",
        "TELEGRAM_NEWS_CHAT_ID",
        "RELAY_STATE_FILE",
        "TELEGRAM_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    spec = importlib.util.spec_from_file_location("relay_loop_test", RELAY_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["relay_loop_test"] = module
    spec.loader.exec_module(module)
    return module


class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_relay_sends_valid_and_drops_malformed(monkeypatch, tmp_path) -> None:
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="tok",
        TELEGRAM_ADMIN_ID="1",
        RELAY_STATE_FILE=str(tmp_path / "state.json"),
    )
    queue = {
        "replies": [
            {"id": "a", "chat_id": "1", "text": "hello"},
            {"id": "b", "chat_id": None, "text": "no chat"},       # malformed
            {"id": "c", "chat_id": "1", "text": ""},               # empty text
            "not-a-dict",                                          # malformed
            {"id": "d", "chat_id": "2", "text": "second"},
        ]
    }

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(relay, "_get", lambda url, timeout=30: json.dumps(queue).encode())
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append((cid, text)) or True
    )
    # The clear call also goes through urllib; stub it out.
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"{}"))

    count = relay.relay_once()
    assert count == 2
    assert sent == [("1", "hello"), ("2", "second")]


def test_relay_is_idempotent_across_ticks(monkeypatch, tmp_path) -> None:
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="tok",
        TELEGRAM_ADMIN_ID="1",
        RELAY_STATE_FILE=str(tmp_path / "state.json"),
    )
    queue = {"replies": [{"id": "x", "chat_id": "1", "text": "once"}]}
    sent: list[str] = []
    monkeypatch.setattr(relay, "_get", lambda url, timeout=30: json.dumps(queue).encode())
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"{}"))

    assert relay.relay_once() == 1
    # Same payload on the next tick must not be re-sent.
    assert relay.relay_once() == 0
    assert sent == ["once"]


def test_relay_state_survives_corrupt_file_and_persists_before_clear(
    monkeypatch, tmp_path
) -> None:
    """The sent ids must be on disk *before* the queue is cleared.

    A failed clear (or a corrupt state file) must never cause a duplicate
    delivery on the next tick.
    """
    state_file = tmp_path / "state.json"
    # A truncated state file means "nothing seen yet", not a crash.
    state_file.write_text('{"sent_ids": [', encoding="utf-8")
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="tok",
        TELEGRAM_ADMIN_ID="1",
        RELAY_STATE_FILE=str(state_file),
    )
    queue = {"replies": [{"id": "x", "chat_id": "1", "text": "once"}]}
    sent: list[str] = []
    monkeypatch.setattr(relay, "_get", lambda url, timeout=30: json.dumps(queue).encode())
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )

    # Make the clear (DELETE) fail: the id must still have been persisted first.
    import urllib.request

    def boom(req, *a, **k):
        raise OSError("clear failed")

    monkeypatch.setattr(urllib.request, "urlopen", boom)

    assert relay.relay_once() == 1
    assert json.loads(state_file.read_text(encoding="utf-8"))["sent_ids"] == ["x"]

    # The queue still holds the reply, but the recorded id stops a re-send.
    assert relay.relay_once() == 0
    assert sent == ["once"]


def test_relay_log_redacts_token(monkeypatch, tmp_path, capsys) -> None:
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="123456:SUPERSECRET",
        TELEGRAM_ADMIN_ID="1",
        RELAY_STATE_FILE=str(tmp_path / "state.json"),
    )
    queue = {"replies": [{"id": "x", "chat_id": "1", "text": "hi"}]}
    monkeypatch.setattr(relay, "_get", lambda url, timeout=30: json.dumps(queue).encode())

    def boom(cid, text):
        relay._log(
            "telegram send failed: "
            + relay._redact("HTTPSConnectionPool /bot123456:SUPERSECRET/sendMessage")
        )
        return False

    monkeypatch.setattr(relay, "_telegram_send", boom)
    relay.relay_once()
    out = capsys.readouterr().out
    assert "SUPERSECRET" not in out


def test_heartbeat_reports_unreachable_honestly(monkeypatch, tmp_path, capsys) -> None:
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="tok",
        TELEGRAM_ADMIN_ID="1",
        RELAY_STATE_FILE=str(tmp_path / "state.json"),
    )
    monkeypatch.setattr(relay, "_get", lambda url, timeout=30: None)
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: captured.update(text=text) or True
    )
    relay.heartbeat()
    assert "unreachable" in captured["text"]
    # It must never claim a check it did not perform.
    assert "never sleeps" not in captured["text"].lower()


def test_heartbeat_skipped_without_admin(monkeypatch, tmp_path, capsys) -> None:
    relay = _load(
        monkeypatch,
        HF_SPACE_URL="https://space.invalid",
        TELEGRAM_BOT_TOKEN="tok",
        RELAY_STATE_FILE=str(tmp_path / "state.json"),
    )
    called = {"n": 0}
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: called.__setitem__("n", called["n"] + 1)
    )
    relay.heartbeat()
    assert called["n"] == 0
    assert "skipped" in capsys.readouterr().out


# --- news digest ----------------------------------------------------------


def _fake_urlopen(body: bytes):
    class _Resp:
        def read(self, _n=None):
            return body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return lambda req, timeout=15: _Resp()


def test_clean_collapses_whitespace_and_unescapes(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    assert relay._clean("  a &amp;\n  b  ") == "a & b"
    assert relay._clean(None) == ""


def test_fetch_feed_titles_parses_and_caps(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "NEWS_MAX_PER_CATEGORY", 2)
    rss = (
        b"<rss><channel>"
        b"<item><title>One &amp; only</title></item>"
        b"<item><title>Two</title></item>"
        b"<item><title>Three</title></item>"
        b"</channel></rss>"
    )
    monkeypatch.setattr(relay.urllib.request, "urlopen", _fake_urlopen(rss))
    assert relay._fetch_feed_titles("https://example.com/feed") == ["One & only", "Two"]


def test_fetch_feed_titles_survives_bad_feed(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")

    def _boom(req, timeout=15):
        raise OSError("network down")

    monkeypatch.setattr(relay.urllib.request, "urlopen", _boom)
    assert relay._fetch_feed_titles("https://example.com/feed") == []


def test_build_news_digest_dedupes_and_bounds(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "NEWS_CATEGORIES", {"A": [("s", "u")], "B": [("s", "u")]})
    monkeypatch.setattr(relay, "_fetch_feed_titles", lambda url: ["Same", "Same", "Unique"])
    digest = relay.build_news_digest()
    assert digest is not None
    assert digest.count("Same") == 1  # deduplicated across categories
    assert "Unique" in digest


def test_build_news_digest_none_when_all_feeds_fail(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "_fetch_feed_titles", lambda url: [])
    assert relay.build_news_digest() is None


def test_build_news_digest_truncates_to_telegram_limit(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "MAX_DIGEST_CHARS", 120)
    monkeypatch.setattr(relay, "NEWS_CATEGORIES", {"A": [("s", "u")]})
    monkeypatch.setattr(relay, "_fetch_feed_titles", lambda url: ["X" * 500])
    digest = relay.build_news_digest()
    assert digest is not None
    assert len(digest) <= 120
    assert digest.endswith("…(trimmed)")


def test_news_digest_sends_one_message_per_category(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "NEWS_SEND_GAP_SECONDS", 0)
    monkeypatch.setattr(
        relay, "build_news_sections", lambda: ["🌍 WORLD\n• a", "💻 TECH\n• b"]
    )
    sent: list[str] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    relay.news_digest()
    assert len(sent) == 2  # one message per category, not a combined digest
    assert "1/2" in sent[0] and "🌍 WORLD" in sent[0]
    assert "2/2" in sent[1] and "💻 TECH" in sent[1]


def test_news_digest_combined_mode_sends_one_message(monkeypatch, tmp_path) -> None:
    relay = _load(
        monkeypatch,
        TELEGRAM_BOT_TOKEN="tok",
        TELEGRAM_ADMIN_ID="42",
        NEWS_SEPARATE_MESSAGES="0",
    )
    monkeypatch.setattr(relay, "build_news_digest", lambda: "combined-body")
    sent: list[str] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    relay.news_digest()
    assert sent == ["combined-body"]


def test_news_digest_skipped_without_admin(monkeypatch, tmp_path, capsys) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    called = {"n": 0}
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: called.__setitem__("n", called["n"] + 1)
    )
    relay.news_digest()
    assert called["n"] == 0
    assert "skipped" in capsys.readouterr().out


# --- market report --------------------------------------------------------


def test_fmt_number_trims_decimals(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    assert relay._fmt_number(22693.4) == "22,693"
    assert relay._fmt_number(94.63) == "94.63"
    assert relay._fmt_number(0.00123) == "0.0012"


def test_fetch_quote_parses_yahoo_shape(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    body = (
        b'{"chart":{"result":[{"meta":{"regularMarketPrice":100.0,'
        b'"chartPreviousClose":98.0}}]}}'
    )
    monkeypatch.setattr(relay.urllib.request, "urlopen", _fake_urlopen(body))
    assert relay._fetch_quote("^NSEI") == (100.0, 98.0)


def test_fetch_quote_survives_bad_symbol(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")

    def _boom(req, timeout=15):
        raise OSError("no route")

    monkeypatch.setattr(relay.urllib.request, "urlopen", _boom)
    assert relay._fetch_quote("^NSEI") is None


def test_build_market_report_shows_arrows_and_pct(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "MARKET_SYMBOLS", [("Up", "A"), ("Down", "B")])
    quotes = {"A": (110.0, 100.0), "B": (90.0, 100.0)}
    monkeypatch.setattr(relay, "_fetch_quote", lambda s: quotes.get(s))
    report = relay.build_market_report()
    assert report is not None
    assert "🟢 Up" in report and "+10.00%" in report
    assert "🔴 Down" in report and "-10.00%" in report
    # The biggest mover is called out explicitly.
    assert "🏆 Top gainer: Up (+10.00%)" in report
    assert "📉 Top loser: Down (-10.00%)" in report


def test_build_market_report_none_when_no_quotes(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "_fetch_quote", lambda s: None)
    assert relay.build_market_report() is None


def test_build_market_report_all_red_never_calls_a_loser_a_gainer(
    monkeypatch, tmp_path
) -> None:
    # A day when every tracked market is down: the "best" mover is still a
    # loss, so it must be labelled honestly and never print a double sign.
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "MARKET_SYMBOLS", [("A", "A"), ("B", "B")])
    quotes = {"A": (99.0, 100.0), "B": (95.0, 100.0)}
    monkeypatch.setattr(relay, "_fetch_quote", lambda s: quotes.get(s))
    report = relay.build_market_report()
    assert report is not None
    assert "+-" not in report
    assert "Top gainer" not in report
    assert "🟢 Best performer: A (-1.00%)" in report
    assert "📉 Top loser: B (-5.00%)" in report


def test_build_market_report_all_green_never_calls_a_winner_a_loser(
    monkeypatch, tmp_path
) -> None:
    # Mirror case: on an all-green day the weakest mover is not a "loser".
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "MARKET_SYMBOLS", [("A", "A"), ("B", "B")])
    quotes = {"A": (101.0, 100.0), "B": (105.0, 100.0)}
    monkeypatch.setattr(relay, "_fetch_quote", lambda s: quotes.get(s))
    report = relay.build_market_report()
    assert report is not None
    assert "Top loser" not in report
    assert "🏆 Top gainer: B (+5.00%)" in report
    assert "🔴 Weakest: A (+1.00%)" in report


def test_market_report_sends_to_news_chat(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "build_market_report", lambda: "market-body")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append((cid, text)) or True
    )
    relay.market_report()
    assert sent == [("42", "market-body")]




# --- AI briefing ----------------------------------------------------------


def test_collect_headlines_dedupes_and_caps(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(
        relay, "NEWS_CATEGORIES", {"A": [("s", "u")], "B": [("s", "u")]}
    )
    monkeypatch.setattr(relay, "_fetch_feed_titles", lambda url: ["Same", "Other"])
    lines = relay.collect_headlines(limit=2)
    assert lines == ["Same (s)", "Other (s)"]


def test_agent_briefing_posts_and_sends(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "collect_headlines", lambda: ["h1"])
    monkeypatch.setattr(relay, "collect_market_lines", lambda: ["Nifty: 1 (+1%)"])
    captured: dict = {}

    def _fake_post(url, payload, timeout=60):
        captured["url"] = url
        captured["payload"] = payload
        return b'{"ok": true, "briefing": "Aaj ka bada news"}'

    monkeypatch.setattr(relay, "_post", _fake_post)
    sent: list[str] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    relay.agent_briefing()
    assert captured["url"].endswith("/api/briefing")
    assert captured["payload"] == {"headlines": ["h1"], "market": ["Nifty: 1 (+1%)"]}
    assert len(sent) == 1 and "Aaj ka bada news" in sent[0]


def test_agent_briefing_skipped_when_space_silent(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "collect_headlines", lambda: ["h1"])
    monkeypatch.setattr(relay, "collect_market_lines", lambda: [])
    monkeypatch.setattr(relay, "_post", lambda url, payload, timeout=60: None)
    sent: list[str] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    relay.agent_briefing()
    assert sent == []


def test_agent_briefing_skipped_when_ai_unavailable(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "collect_headlines", lambda: ["h1"])
    monkeypatch.setattr(relay, "collect_market_lines", lambda: [])
    monkeypatch.setattr(
        relay, "_post", lambda url, payload, timeout=60: b'{"ok": false}'
    )
    sent: list[str] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append(text) or True
    )
    relay.agent_briefing()
    assert sent == []


# --- Weather ---------------------------------------------------------------


def test_build_weather_report_formats(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "WEATHER_CITY", "Delhi")
    monkeypatch.setattr(relay, "WEATHER_PLACES", [("Delhi", 28.6, 77.2)])
    monkeypatch.setattr(
        relay,
        "_fetch_weather",
        lambda lat, lon: {"temp": 31.4, "code": 61, "tmax": 34.0, "tmin": 27.0, "rain": 40},
    )
    report = relay.build_weather_report()
    assert report is not None
    assert "Delhi" in report
    assert "Light rain" in report
    assert "31°C" in report
    assert "rain 40%" in report


def test_build_weather_report_none_when_no_data(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok")
    monkeypatch.setattr(relay, "WEATHER_PLACES", [("Delhi", 28.6, 77.2)])
    monkeypatch.setattr(relay, "_fetch_weather", lambda lat, lon: None)
    assert relay.build_weather_report() is None


def test_weather_report_sends_to_news_chat(monkeypatch, tmp_path) -> None:
    relay = _load(monkeypatch, TELEGRAM_BOT_TOKEN="tok", TELEGRAM_ADMIN_ID="42")
    monkeypatch.setattr(relay, "build_weather_report", lambda: "weather-body")
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        relay, "_telegram_send", lambda cid, text: sent.append((cid, text)) or True
    )
    relay.weather_report()
    assert sent == [("42", "weather-body")]

