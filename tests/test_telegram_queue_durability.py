"""Durability and integrity of the Telegram queue files.

The reply, command and task queues live on disk because the relay (a separate
GitHub Actions job) reads what the webhook wrote. Three properties matter:

- a queued entry survives a process restart if the directory is durable,
- a crash mid-write never leaves a half-written file (which would discard the
  whole queue on the next read),
- two concurrent appends do not lose one another.

These tests drive the real helpers in web/app.py. No infrastructure is faked:
the durability question itself (the HF free tier has no persistent volume) is
documented rather than asserted, because it depends on the deployment.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def appmod(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    return appmod


def test_queue_dir_defaults_to_tmp(monkeypatch) -> None:
    """Unset must keep the historical /tmp location, not invent a new one."""
    import web.app as appmod

    monkeypatch.delenv("TELEGRAM_QUEUE_DIR", raising=False)
    assert appmod._queue_dir() == "/tmp"


def test_queue_dir_honours_the_env_var(monkeypatch, tmp_path) -> None:
    """An operator can point the queues at a durable mount without a code change."""
    import web.app as appmod

    target = tmp_path / "durable"
    monkeypatch.setenv("TELEGRAM_QUEUE_DIR", str(target))
    assert appmod._queue_dir() == str(target)
    assert target.is_dir(), "the directory must be created if it does not exist"


def test_queue_dir_falls_back_when_the_path_is_unusable(monkeypatch, tmp_path) -> None:
    """A bad path must not take the webhook down; it degrades to /tmp."""
    import web.app as appmod

    blocker = tmp_path / "a-file"
    blocker.write_text("not a directory")
    monkeypatch.setenv("TELEGRAM_QUEUE_DIR", str(blocker / "nested"))
    assert appmod._queue_dir() == "/tmp"


def test_append_round_trips_through_the_file(appmod) -> None:
    """A queued reply is readable by a later reader, with its dedup id."""
    appmod._append_queue(appmod.TELEGRAM_REPLY_QUEUE, 123, "hello")
    appmod._append_queue(appmod.TELEGRAM_REPLY_QUEUE, 123, "world")
    entries = appmod._read_queue(appmod.TELEGRAM_REPLY_QUEUE)
    assert [e["text"] for e in entries] == ["hello", "world"]
    assert all(e["id"] for e in entries)
    assert len({e["id"] for e in entries}) == 2, "ids must be unique for dedup"


def test_a_corrupt_file_does_not_lose_the_next_append(appmod) -> None:
    """A truncated write must not permanently poison the queue."""
    path = appmod.TELEGRAM_REPLY_QUEUE
    Path(path).write_text('{"not": "a list"}')
    # A non-list body reads as empty (and is logged), then a new append works.
    assert appmod._read_queue(path) == []
    appmod._append_queue(path, 1, "after corruption")
    assert [e["text"] for e in appmod._read_queue(path)] == ["after corruption"]


def test_write_queue_is_atomic(appmod, monkeypatch) -> None:
    """A failure mid-write must leave the previous queue intact, not a stub."""
    path = appmod.TELEGRAM_REPLY_QUEUE
    appmod._append_queue(path, 1, "original")
    before = Path(path).read_text()

    real_dump = json.dump

    def _explode(obj, f, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(json, "dump", _explode)
    with pytest.raises(OSError):
        appmod._append_queue(path, 2, "should not land")
    monkeypatch.setattr(json, "dump", real_dump)

    assert Path(path).read_text() == before, "the old queue must survive a failed write"
    assert [e["text"] for e in appmod._read_queue(path)] == ["original"]
    # No temp file is left behind.
    leftovers = [p for p in os.listdir(os.path.dirname(path)) if p.startswith(".queue-")]
    assert leftovers == []


def test_concurrent_appends_do_not_lose_entries(appmod) -> None:
    """The webhook is multi-threaded; a read-modify-write race must be closed."""
    path = appmod.TELEGRAM_REPLY_QUEUE
    n = 40
    threads = [
        threading.Thread(target=appmod._append_queue, args=(path, i, f"m{i}"))
        for i in range(n)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    entries = appmod._read_queue(path)
    assert len(entries) == n, f"lost entries: {len(entries)} of {n}"
    assert {e["text"] for e in entries} == {f"m{i}" for i in range(n)}


def test_task_queue_update_is_atomic(appmod) -> None:
    """A work-order state patch must persist and stay readable."""
    appmod._append_task({"id": "t1", "state": "queued", "instruction": "x"})
    updated = appmod._update_task("t1", state="running")
    assert updated["state"] == "running"
    on_disk = appmod._read_task_queue()
    assert on_disk[0]["state"] == "running"
    assert on_disk[0]["instruction"] == "x", "a patch must not drop other fields"
    assert appmod._update_task("missing", state="done") is None


def test_queue_stays_bounded(appmod) -> None:
    """An unbounded queue file would grow without limit on a busy chat."""
    appmod.TELEGRAM_QUEUE_MAX = 5
    for i in range(12):
        appmod._append_queue(appmod.TELEGRAM_REPLY_QUEUE, 1, f"m{i}")
    entries = appmod._read_queue(appmod.TELEGRAM_REPLY_QUEUE)
    assert len(entries) == 5
    assert [e["text"] for e in entries] == [f"m{i}" for i in range(7, 12)]
