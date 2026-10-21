"""Static checks on the relay/heartbeat workflows.

GitHub-hosted execution is not available here, so these read the workflow files
directly and assert the properties the review depends on: an explicit
least-privilege ``permissions`` block, a concurrency group that serialises runs,
and no token ever written into the file. No YAML parser is used (the repository
does not vendor one); the checks are simple textual invariants on purpose.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
KEEPALIVE = WORKFLOWS / "keepalive.yml"
HEARTBEAT = WORKFLOWS / "heartbeat.yml"


def test_workflows_exist() -> None:
    assert KEEPALIVE.is_file()
    assert HEARTBEAT.is_file()


def test_keepalive_declares_permissions_and_concurrency() -> None:
    text = KEEPALIVE.read_text(encoding="utf-8")
    assert re.search(r"^permissions:", text, re.M)
    assert "contents: read" in text
    assert re.search(r"^concurrency:", text, re.M)
    assert "cancel-in-progress: false" in text


def test_heartbeat_has_concurrency_and_permissions() -> None:
    text = HEARTBEAT.read_text(encoding="utf-8")
    assert re.search(r"^permissions:", text, re.M)
    assert "contents: read" in text
    assert re.search(r"^concurrency:", text, re.M)


def test_no_token_literal_in_workflows() -> None:
    # Secrets must come from ${{ secrets.* }}, never a literal.
    literal = re.compile(r"(ghp_[A-Za-z0-9]{20,}|bot[0-9]{6,}:[A-Za-z0-9_-]{20,})")
    for path in (KEEPALIVE, HEARTBEAT):
        assert not literal.search(path.read_text(encoding="utf-8")), path


def test_relay_script_present_and_heartbeat_mode() -> None:
    script = WORKFLOWS.parent.parent / "scripts" / "relay_loop.py"
    text = script.read_text(encoding="utf-8")
    assert '"heartbeat"' in text or "'heartbeat'" in text
    assert "TELEGRAM_ADMIN_ID" in text
