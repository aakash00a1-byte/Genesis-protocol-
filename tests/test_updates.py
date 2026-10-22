"""Tests for the human-approved update pipeline.

Covers the command grammar, token resolution, and the GitHub PR transport
against a fake HTTP layer (no network). The central invariant: nothing is
merged without an explicit approve, and only agent branches are approvable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from genesis_protocol.updates import (
    Update,
    handle_command,
    newest,
    parse_command,
    render_list,
    resolve,
)
from genesis_protocol.updates.github_prs import GitHubPRTransport


# ------------------------------------------------------------------
# Command grammar
# ------------------------------------------------------------------
def test_parse_recognised_commands() -> None:
    assert parse_command("/approve 3") == ("approve", "3")
    assert parse_command("/reject upd-abc why not") == ("reject", "upd-abc why not")
    assert parse_command("/updates") == ("updates", "")
    assert parse_command("  /LIST  ") == ("list", "")


def test_parse_ignores_ordinary_text() -> None:
    assert parse_command("hello there") is None
    assert parse_command("/ask what is up") is None
    assert parse_command("") is None
    assert parse_command(None) is None  # type: ignore[arg-type]


def test_resolve_by_number_id_and_prefix() -> None:
    items = [Update(id="101", title="a"), Update(id="202", title="b")]
    assert resolve(items, "1").id == "101"
    assert resolve(items, "2").id == "202"
    assert resolve(items, "101").id == "101"
    assert resolve(items, "9") is None
    assert resolve(items, "2") is not None


def test_resolve_ambiguous_prefix_is_none() -> None:
    items = [Update(id="abc1", title="a"), Update(id="abc2", title="b")]
    assert resolve(items, "abc") is None


# ------------------------------------------------------------------
# A fake transport drives the command layer
# ------------------------------------------------------------------
class FakeTransport:
    def __init__(self, items=None) -> None:
        self.items = items or []
        self.approved: list[str] = []
        self.rejected: list[str] = []

    def list_open(self):
        return self.items

    def approve(self, token, reason=""):
        item = resolve(self.items, token)
        if item is None:
            return f"Update '{token}' nahi mila (ya already decided)."
        self.approved.append(item.id)
        self.items = [i for i in self.items if i.id != item.id]
        return f"✅ Approved & merged: {item.title}"

    def reject(self, token, reason=""):
        item = resolve(self.items, token)
        if item is None:
            return f"Update '{token}' nahi mila (ya already decided)."
        self.rejected.append(item.id)
        self.items = [i for i in self.items if i.id != item.id]
        return f"❌ Rejected & closed: {item.title}"

    def status(self, token):
        item = resolve(self.items, token)
        return f"#{item.id}" if item else f"Update '{token}' nahi mila."


def test_handle_command_approve_and_reject() -> None:
    transport = FakeTransport([Update(id="7", title="fix relay")])
    assert "Approved" in handle_command("/approve 1", transport)
    assert transport.approved == ["7"]
    # A second approve finds nothing.
    assert "nahi mila" in handle_command("/approve 1", transport)

    transport = FakeTransport([Update(id="8", title="fix web")])
    assert "Rejected" in handle_command("/reject 8", transport)
    assert transport.rejected == ["8"]


def test_newest_picks_highest_pr_number() -> None:
    items = [Update(id="14", title="a"), Update(id="17", title="b"), Update(id="16", title="c")]
    assert newest(items).id == "17"
    assert newest([]) is None


def test_bare_approve_targets_the_newest_update() -> None:
    """Tapping the command in a notification sends only ``/approve``.

    That must land the newest proposal, not print a usage error and strand the
    owner — the failure mode seen when #17 was tapped but never merged.
    """
    transport = FakeTransport([Update(id="14", title="older"), Update(id="17", title="newest")])
    reply = handle_command("/approve", transport)
    assert "17" in reply
    assert transport.approved == ["17"]
    # The older one is untouched.
    assert [u.id for u in transport.list_open()] == ["14"]


def test_bare_approve_with_nothing_pending_is_honest() -> None:
    transport = FakeTransport([])
    assert "Koi pending update nahi hai" in handle_command("/approve", transport)


def test_bare_reject_targets_the_newest_update() -> None:
    transport = FakeTransport([Update(id="14", title="older"), Update(id="17", title="newest")])
    reply = handle_command("/reject", transport)
    assert transport.rejected == ["17"]
    assert "17" in reply



def test_handle_command_list_and_help() -> None:
    transport = FakeTransport([])
    assert handle_command("/updates", transport) == "Koi pending update nahi hai."
    assert "commands" in (handle_command("/help", transport) or "").lower()


def test_handle_command_returns_none_for_other_text() -> None:
    assert handle_command("just chatting", FakeTransport([])) is None


def test_handle_command_reports_action_errors() -> None:
    class Boom(FakeTransport):
        def approve(self, token, reason=""):
            raise RuntimeError("merge blocked by branch protection")

    reply = handle_command("/approve 1", Boom([Update(id="1", title="x")]))
    assert "merge blocked" in reply


def test_render_list_shows_numbered_ids() -> None:
    text = render_list([Update(id="101", title="a"), Update(id="102", title="b")])
    assert "1. #101" in text and "2. #102" in text


# ------------------------------------------------------------------
# GitHub PR transport (fake HTTP, no network)
# ------------------------------------------------------------------
def _pr(number, title, branch="agent/self-improve-x", url=None):
    return {
        "number": number,
        "title": title,
        "head": {"ref": branch},
        "html_url": url or f"https://github.com/o/r/pull/{number}",
    }


def test_transport_lists_only_agent_branches() -> None:
    calls = []

    def http(method, url, payload):
        calls.append((method, url, payload))
        return [_pr(1, "agent work"), _pr(2, "human work", branch="feature/human")]

    transport = GitHubPRTransport("o/r", "tok", http=http)
    items = transport.list_open()
    assert [i.id for i in items] == ["1"]


def test_transport_approve_merges_squash() -> None:
    calls = []

    def http(method, url, payload):
        calls.append((method, url, payload))
        if method == "GET":
            return [_pr(5, "improve docs")]
        return {"merged": True, "sha": "abc123"}

    transport = GitHubPRTransport("o/r", "tok", http=http)
    reply = transport.approve("1")
    assert "Approved & merged" in reply
    merge = [c for c in calls if c[0] == "PUT"][0]
    assert merge[2]["merge_method"] == "squash"
    assert "/pulls/5/merge" in merge[1]


def test_transport_approve_reports_merge_failure() -> None:
    def http(method, url, payload):
        if method == "GET":
            return [_pr(5, "improve docs")]
        return {"merged": False, "message": "Pull Request is not mergeable"}

    transport = GitHubPRTransport("o/r", "tok", http=http)
    assert "not mergeable" in transport.approve("5")


def test_transport_calls_on_merged_after_success() -> None:
    merged: list[str] = []

    def http(method, url, payload):
        if method == "GET":
            return [_pr(6, "ship it")]
        return {"merged": True, "sha": "deadbeef"}

    transport = GitHubPRTransport(
        "o/r", "tok", http=http, on_merged=lambda item: merged.append(item.id)
    )
    transport.approve("6")
    assert merged == ["6"]


def test_transport_on_merged_not_called_when_merge_fails() -> None:
    merged: list[str] = []

    def http(method, url, payload):
        if method == "GET":
            return [_pr(6, "ship it")]
        return {"merged": False}

    transport = GitHubPRTransport(
        "o/r", "tok", http=http, on_merged=lambda item: merged.append(item.id)
    )
    transport.approve("6")
    assert merged == []


def test_transport_reject_closes_pr() -> None:
    calls = []

    def http(method, url, payload):
        calls.append((method, url, payload))
        if method == "GET":
            return [_pr(9, "bad idea")]
        return {}

    transport = GitHubPRTransport("o/r", "tok", http=http)
    reply = transport.reject("9", "not needed")
    assert "Rejected" in reply
    patch = [c for c in calls if c[0] == "PATCH"][0]
    assert patch[2]["state"] == "closed"


def test_transport_approve_unknown_token() -> None:
    transport = GitHubPRTransport("o/r", "tok", http=lambda *a: [])
    assert "nahi mila" in transport.approve("99")


def test_leaf_import_does_not_load_the_whole_app() -> None:
    """Importing the update pipeline must stay stdlib-only.

    The self-improvement harness runs with nothing but the standard library;
    an eager ``genesis_protocol/__init__`` once pulled in python-dotenv through
    ``config`` and broke every /approve with an ImportError.
    """
    import subprocess

    root = str(Path(__file__).resolve().parent.parent)
    code = (
        f"import sys; sys.path.insert(0, r'{root}');"
        "import genesis_protocol.updates;"
        "print('dotenv' in sys.modules or 'genesis_protocol.config' in sys.modules)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False", out.stdout
