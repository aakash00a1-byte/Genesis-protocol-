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
