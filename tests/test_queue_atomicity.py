"""Queue persistence hardening: atomic writes and process-safe locking.

The Telegram queues are read-modify-write files shared by the web process (the
only writer) and its request threads. Before this change a plain open(path,'w')
truncated the file before writing, so a crash or a full disk mid-write left
invalid JSON that the next read discarded, and two concurrent appends could both
read the same queue and drop one entry.

These tests exercise the real code paths with the queue files redirected to a
temp dir. No Telegram, GitHub merge or deployment API is contacted.
"""
from __future__ import annotations

import fcntl
import json
import multiprocessing as mp
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OWNER = "1863492058"
STRANGER = "999999999"


def _mp_append_worker(path: str, prefix: str, n: int) -> None:
    """Append ``n`` entries in a forked child; the queue lock must serialise it."""
    import web.app as appmod

    for i in range(n):
        appmod._append_queue(path, prefix, f"{prefix}-{i}")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("GENESIS_ENV", "TELEGRAM_WEBHOOK_SECRET", "TELEGRAM_ADMIN_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def appmod():
    import web.app as module

    return module


@pytest.fixture
def paths(tmp_path):
    return {
        "reply": str(tmp_path / "replies.json"),
        "command": str(tmp_path / "commands.json"),
        "task": str(tmp_path / "tasks.json"),
    }


@pytest.fixture
def client(appmod, paths, monkeypatch):
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", paths["reply"])
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", paths["command"])
    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", paths["task"])
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _read(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


def _msg(text, from_id=OWNER, chat_id=OWNER):
    return {"message": {"text": text, "from": {"id": from_id}, "chat": {"id": chat_id}}}


# ---------------------------------------------------------------------------
# Concurrency: no entry is lost
# ---------------------------------------------------------------------------
def test_concurrent_threads_do_not_lose_entries(appmod, paths):
    path = paths["command"]
    writers, per_writer = 6, 20
    with ThreadPoolExecutor(max_workers=writers) as pool:
        list(
            pool.map(
                lambda w: [appmod._append_queue(path, w, f"t{w}-{i}") for i in range(per_writer)],
                range(writers),
            )
        )
    queue = _read(path)
    assert len(queue) == writers * per_writer
    assert len({e["text"] for e in queue}) == writers * per_writer


def test_concurrent_processes_do_not_lose_entries(appmod, paths):
    if "fork" not in mp.get_all_start_methods():
        pytest.skip("fork start method unavailable; cannot test cross-process locking")
    path = paths["command"]
    writers, per_writer = 4, 25
    ctx = mp.get_context("fork")
    procs = [
        ctx.Process(target=_mp_append_worker, args=(path, f"p{k}", per_writer))
        for k in range(writers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert [p.exitcode for p in procs] == [0] * writers
    queue = _read(path)
    assert len(queue) == writers * per_writer
    assert len({e["text"] for e in queue}) == writers * per_writer


# ---------------------------------------------------------------------------
# Atomic write: an interrupted write must not corrupt the previous queue
# ---------------------------------------------------------------------------
def test_interrupted_write_keeps_previous_queue_intact(appmod, paths, monkeypatch):
    path = paths["command"]
    appmod._append_queue(path, OWNER, "first")
    before = _read(path)
    assert [e["text"] for e in before] == ["first"]

    def _boom(_fd):
        raise OSError("simulated disk failure before replace")

    monkeypatch.setattr(appmod.os, "fsync", _boom)
    with pytest.raises(OSError):
        appmod._append_queue(path, OWNER, "second")

    # Previous valid queue is untouched, and no temp file was left behind.
    assert _read(path) == before
    leftovers = [p.name for p in Path(path).parent.glob(".queue-*")]
    assert leftovers == []


def test_write_uses_atomic_replace(appmod, paths, monkeypatch):
    path = paths["command"]
    replaced = {"n": 0}
    real_replace = os.replace

    def _counting_replace(src, dst):
        replaced["n"] += 1
        return real_replace(src, dst)

    monkeypatch.setattr(appmod.os, "replace", _counting_replace)
    appmod._append_queue(path, OWNER, "x")
    assert replaced["n"] == 1
    assert _read(path)[0]["text"] == "x"


# ---------------------------------------------------------------------------
# Malformed data fails safely and is never silently discarded
# ---------------------------------------------------------------------------
def test_malformed_json_is_quarantined_not_discarded(appmod, paths):
    path = Path(paths["command"])
    path.write_text("{ this is not json")
    original = path.read_bytes()

    # The write must still succeed for the caller...
    appmod._append_queue(str(path), OWNER, "after-corruption")

    # ...and the unreadable bytes must be preserved, not lost.
    backups = list(path.parent.glob("commands.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == original

    queue = _read(str(path))
    assert [e["text"] for e in queue] == ["after-corruption"]


def test_non_list_json_is_quarantined(appmod, paths):
    path = Path(paths["command"])
    path.write_text('{"not": "a list"}')
    appmod._append_queue(str(path), OWNER, "entry")
    backups = list(path.parent.glob("commands.json.corrupt-*"))
    assert len(backups) == 1
    assert [e["text"] for e in _read(str(path))] == ["entry"]


def test_read_queue_still_degrades_gracefully(appmod, paths):
    # The read path used by the GET endpoints must not raise on bad data.
    path = Path(paths["command"])
    path.write_text("{ broken")
    assert appmod._read_queue(str(path)) == []


# ---------------------------------------------------------------------------
# Existing entries and ordering are preserved
# ---------------------------------------------------------------------------
def test_existing_entries_and_order_preserved(appmod, paths):
    path = paths["command"]
    for text in ("a", "b", "c"):
        appmod._append_queue(path, OWNER, text)
    appmod._append_queue(path, OWNER, "d")
    assert [e["text"] for e in _read(path)] == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# Lock timeout / failure must not proceed as if the write succeeded
# ---------------------------------------------------------------------------
def test_lock_timeout_raises_and_does_not_write(appmod, paths, monkeypatch):
    path = paths["command"]
    monkeypatch.setattr(appmod, "TELEGRAM_QUEUE_LOCK_TIMEOUT", 0.1)

    holder = os.open(path + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(appmod.QueueLockError):
            appmod._append_queue(path, OWNER, "should-not-appear")
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)

    assert _read(path) is None  # nothing was written


def test_lock_timeout_on_command_endpoint_returns_500(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    monkeypatch.setattr(appmod, "TELEGRAM_QUEUE_LOCK_TIMEOUT", 0.1)

    holder = os.open(paths["command"] + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"))
    finally:
        fcntl.flock(holder, fcntl.LOCK_UN)
        os.close(holder)

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["ok"] is False
    assert _read(paths["command"]) is None  # a lost /approve is not a silent success


# ---------------------------------------------------------------------------
# Authorization still holds after the queue rewrite
# ---------------------------------------------------------------------------
def test_authorized_owner_approval_still_works(client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7"))
    assert resp.get_json()["queued"] == "command"
    queue = _read(paths["command"])
    assert queue[0]["text"] == "/approve 7"
    assert str(queue[0]["from_id"]) == OWNER


def test_unauthorized_sender_is_denied_and_not_queued(client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    resp = client.post("/api/telegram/webhook", json=_msg("/approve 7", from_id=STRANGER))
    assert resp.get_json()["denied"] == "not-owner"
    assert _read(paths["command"]) is None


def test_harness_rejects_unauthorized_queued_entry(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("self_improve", ROOT / "scripts" / "self_improve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    payload = {
        "commands": [
            {"text": "/approve 7", "from_id": STRANGER},
            {"text": "/approve 8", "from_id": OWNER},
            {"text": "/approve 9"},
        ]
    }
    monkeypatch.setattr(module, "_space_get", lambda url: json.dumps(payload))
    assert module._incoming_commands() == ["/approve 8"]


# ---------------------------------------------------------------------------
# Drain by id: a writer racing a drain must never lose an entry
# ---------------------------------------------------------------------------
def test_ack_queue_removes_only_acknowledged_ids(appmod, paths):
    path = paths["command"]
    for text in ("a", "b", "c"):
        appmod._append_queue(path, OWNER, text)
    ids = [e["id"] for e in _read(path)]
    removed = appmod._ack_queue(path, [ids[0], ids[2]])
    assert removed == 2
    assert [e["text"] for e in _read(path)] == ["b"]


def test_ack_queue_unknown_id_is_harmless(appmod, paths):
    path = paths["command"]
    appmod._append_queue(path, OWNER, "keep")
    assert appmod._ack_queue(path, ["does-not-exist"]) == 0
    assert [e["text"] for e in _read(path)] == ["keep"]


def test_ack_queue_empty_ids_is_noop(appmod, paths):
    path = paths["command"]
    appmod._append_queue(path, OWNER, "keep")
    assert appmod._ack_queue(path, []) == 0
    assert [e["text"] for e in _read(path)] == ["keep"]


def test_entry_appended_during_drain_survives_ack(appmod, paths):
    """The lost-entry race: a command arriving mid-drain must not be wiped.

    The drain reads the queue, acts, then acknowledges the ids it saw. An entry
    appended after the read is not in the ack set, so it must remain for the
    next tick instead of being cleared with the batch.
    """
    path = paths["command"]
    appmod._append_queue(path, OWNER, "old")
    drained_ids = [e["id"] for e in appmod._read_queue(path)]  # what the drain saw
    appmod._append_queue(path, OWNER, "new")  # arrives while the drain works
    appmod._ack_queue(path, drained_ids)
    remaining = [e["text"] for e in _read(path)]
    assert remaining == ["new"]


def test_drain_endpoint_acks_by_id_and_keeps_new(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    header = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}

    # Owner queues one command; the harness reads it.
    client.post("/api/telegram/webhook", json=_msg("/approve 7"), headers=header)
    first = client.get("/api/telegram/commands", headers=header).get_json()["commands"]
    assert len(first) == 1

    # A second command arrives while the harness is acting on the first.
    client.post("/api/telegram/webhook", json=_msg("/reject 8"), headers=header)

    # The harness acknowledges only what it read.
    resp = client.delete(
        "/api/telegram/commands", json={"ids": [first[0]["id"]]}, headers=header
    )
    assert resp.get_json()["removed"] == 1
    remaining = client.get("/api/telegram/commands", headers=header).get_json()["commands"]
    assert [e["text"] for e in remaining] == ["/reject 8"]


def test_drain_endpoint_without_body_still_clears_all(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    header = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    client.post("/api/telegram/webhook", json=_msg("/approve 7"), headers=header)
    resp = client.delete("/api/telegram/commands", headers=header)
    assert resp.get_json()["cleared"] is True
    assert client.get("/api/telegram/commands", headers=header).get_json()["commands"] == []


def test_drain_endpoint_requires_auth(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    assert client.delete("/api/telegram/commands", json={"ids": ["x"]}).status_code == 401


def test_drain_endpoint_rejects_non_list_ids(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    header = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    resp = client.delete("/api/telegram/commands", json={"ids": "nope"}, headers=header)
    assert resp.status_code == 400


def test_reply_drain_acks_only_sent_ids(appmod, client, paths, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    header = {"X-Telegram-Bot-Api-Secret-Token": "s3cret"}
    appmod._append_queue(paths["reply"], OWNER, "r1")
    seen = appmod._read_reply_queue()
    appmod._append_queue(paths["reply"], OWNER, "r2")  # arrives mid-drain
    resp = client.delete(
        "/api/telegram/queue", json={"ids": [seen[0]["id"]]}, headers=header
    )
    assert resp.get_json()["removed"] == 1
    left = client.get("/api/telegram/queue", headers=header).get_json()["replies"]
    assert [e["text"] for e in left] == ["r2"]


def test_harness_ack_commands_sends_ids_not_a_clear(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("self_improve", ROOT / "scripts" / "self_improve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[tuple] = []
    monkeypatch.setattr(module, "_space_send", lambda *a, **k: calls.append((a, k)))
    module._ack_commands(["1", "2"])
    assert calls, "ack must call the Space"
    args, kwargs = calls[0]
    assert args[0] == "DELETE"
    assert args[2] == {"ids": ["1", "2"]}
    # Nothing to ack means no call at all.
    calls.clear()
    module._ack_commands([])
    assert calls == []


def test_harness_incoming_entries_keep_ids(monkeypatch):
    import importlib.util

    spec = importlib.util.spec_from_file_location("self_improve", ROOT / "scripts" / "self_improve.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", OWNER)
    payload = {
        "commands": [
            {"id": "s1", "text": "/approve 7", "from_id": STRANGER},
            {"id": "o1", "text": "/approve 8", "from_id": OWNER},
        ]
    }
    monkeypatch.setattr(module, "_space_get", lambda url: json.dumps(payload))
    entries = module._incoming_command_entries()
    assert entries == [{"id": "o1", "text": "/approve 8", "from_id": OWNER}]
    assert module._incoming_commands() == ["/approve 8"]
