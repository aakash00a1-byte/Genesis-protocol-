"""Unit tests for autonomous run state + atomic, redacting checkpoints."""
from __future__ import annotations

import json
import os

from genesis.autonomy.state import TaskState, TaskStatus, TaskStore


def test_state_round_trips_through_disk(tmp_path) -> None:
    store = TaskStore(str(tmp_path))
    state = TaskState(task="do a thing", actor="a", role="coder")
    state.iteration = 2
    state.add_checkpoint(status=TaskStatus.RUNNING)
    state.add_checkpoint(status=TaskStatus.SUCCEEDED, result="done")

    path = store.save(state)
    assert os.path.exists(path)

    loaded = store.load(state.run_id)
    assert loaded is not None
    assert loaded.task == "do a thing"
    assert loaded.iteration == 2
    assert loaded.status is TaskStatus.SUCCEEDED
    assert [c.status for c in loaded.checkpoints] == ["running", "succeeded"]


def test_checkpoint_is_redacted_on_disk(tmp_path) -> None:
    store = TaskStore(str(tmp_path))
    state = TaskState(task="use sk-abcdef0123456789abcdef to call the API")
    state.result = {"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}
    path = store.save(state)

    raw = open(path, encoding="utf-8").read()
    assert "sk-abcdef0123456789abcdef" not in raw
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in raw
    # The file is still valid JSON after redaction.
    json.loads(raw)


def test_terminal_states_are_not_resumable(tmp_path) -> None:
    store = TaskStore(str(tmp_path))
    for status, resumable in [
        (TaskStatus.SUCCEEDED, False),
        (TaskStatus.BLOCKED, False),
        (TaskStatus.FAILED, True),
        (TaskStatus.INTERRUPTED, True),
        (TaskStatus.LIMIT_REACHED, True),
        (TaskStatus.RUNNING, True),
    ]:
        state = TaskState()
        state.status = status
        store.save(state)
        assert store.load(state.run_id).resumable is resumable, status


def test_missing_run_returns_none(tmp_path) -> None:
    store = TaskStore(str(tmp_path))
    assert store.load("run-does-not-exist") is None
    assert not store.exists("run-does-not-exist")


def test_run_id_path_traversal_is_neutralised(tmp_path) -> None:
    store = TaskStore(str(tmp_path))
    state = TaskState(run_id="../../etc/passwd")
    path = store.save(state)
    # The file must stay inside the store directory.
    assert os.path.dirname(os.path.abspath(path)) == os.path.abspath(str(tmp_path))
