"""Webhook routing for owner work orders (/do, /tasks, /cancel).

The Space webhook parks a /do order on the task queue and acknowledges the
owner; it never runs the agent or merges. These tests drive the real Flask
route with the queue files redirected to a temp dir.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import web.app as appmod

    monkeypatch.setattr(appmod, "TELEGRAM_TASK_QUEUE", str(tmp_path / "tasks.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_REPLY_QUEUE", str(tmp_path / "replies.json"))
    monkeypatch.setattr(appmod, "TELEGRAM_COMMAND_QUEUE", str(tmp_path / "commands.json"))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _msg(text, chat_id=1863492058):
    return {"message": {"text": text, "from": {"id": chat_id}, "chat": {"id": chat_id}}}


def _read(path):
    return json.loads(path.read_text()) if path.exists() else []


def test_do_parks_a_work_order_and_acknowledges(client, tmp_path):
    resp = client.post("/api/telegram/webhook", json=_msg("/do fix the login bug"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["queued"] == "work-order"
    order_id = body["id"]

    tasks = _read(tmp_path / "tasks.json")
    assert len(tasks) == 1
    assert tasks[0]["id"] == order_id
    assert tasks[0]["instruction"] == "fix the login bug"
    assert tasks[0]["state"] == "queued"

    replies = _read(tmp_path / "replies.json")
    assert any(order_id in r["text"] for r in replies)


def test_do_without_instruction_asks_for_one(client, tmp_path):
    resp = client.post("/api/telegram/webhook", json=_msg("/do"))
    assert resp.status_code == 200
    assert resp.get_json()["queued"] == "do-help"
    assert _read(tmp_path / "tasks.json") == []


def test_tasks_lists_orders(client, tmp_path):
    client.post("/api/telegram/webhook", json=_msg("/do write a test"))
    resp = client.post("/api/telegram/webhook", json=_msg("/tasks"))
    assert resp.get_json()["queued"] == "tasks"
    replies = _read(tmp_path / "replies.json")
    assert any("write a test" in r["text"] for r in replies)


def test_cancel_marks_order_cancelled(client, tmp_path):
    order_id = client.post("/api/telegram/webhook", json=_msg("/do refactor x")).get_json()["id"]
    client.post("/api/telegram/webhook", json=_msg(f"/cancel {order_id}"))
    tasks = _read(tmp_path / "tasks.json")
    assert tasks[0]["state"] == "cancelled"


def test_do_is_not_treated_as_an_approval_command(client, tmp_path):
    client.post("/api/telegram/webhook", json=_msg("/do improve docs"))
    # Nothing should have been parked on the approval command queue.
    assert _read(tmp_path / "commands.json") == []


def test_tasks_endpoint_patch_and_get(client, tmp_path):
    order_id = client.post("/api/telegram/webhook", json=_msg("/do do a thing")).get_json()["id"]
    got = client.get("/api/telegram/tasks").get_json()
    assert got["count"] == 1

    patched = client.patch("/api/telegram/tasks", json={"id": order_id, "state": "done", "pr": "http://x/1"})
    assert patched.status_code == 200
    assert patched.get_json()["task"]["state"] == "done"

    missing = client.patch("/api/telegram/tasks", json={"id": "nope", "state": "done"})
    assert missing.status_code == 404
