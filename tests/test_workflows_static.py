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
DEPLOY = WORKFLOWS / "deploy-space.yml"


def test_workflows_exist() -> None:
    assert KEEPALIVE.is_file()
    assert HEARTBEAT.is_file()
    assert DEPLOY.is_file()


def test_deploy_workflow_mirrors_to_space() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert re.search(r"^permissions:", text, re.M)
    assert "contents: read" in text
    assert re.search(r"^concurrency:", text, re.M)
    # Deploy must run the shared mirror script with the secret, never a literal.
    assert "bash scripts/hf_deploy.sh" in text
    assert "${{ secrets.HF_TOKEN }}" in text


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
    literal = re.compile(
        r"(ghp_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|bot[0-9]{6,}:[A-Za-z0-9_-]{20,})"
    )
    for path in (KEEPALIVE, HEARTBEAT, DEPLOY):
        assert not literal.search(path.read_text(encoding="utf-8")), path


def test_relay_script_present_and_heartbeat_mode() -> None:
    script = WORKFLOWS.parent.parent / "scripts" / "relay_loop.py"
    text = script.read_text(encoding="utf-8")
    assert '"heartbeat"' in text or "'heartbeat'" in text
    assert "TELEGRAM_ADMIN_ID" in text


# -- every workflow runs with least privilege --------------------------------
ALL_WORKFLOWS = sorted(WORKFLOWS.glob("*.yml"))


def test_every_workflow_declares_a_permissions_block() -> None:
    """An absent block inherits the repository default, which may be read-write.

    Every workflow here only reads code, builds or tests, so the token must not
    silently carry write access.
    """
    missing = [
        path.name
        for path in ALL_WORKFLOWS
        if not re.search(r"(?m)^permissions:", path.read_text(encoding="utf-8"))
    ]
    assert not missing, f"workflows without a permissions block: {missing}"


def test_no_workflow_grants_write_all() -> None:
    offenders = [
        path.name
        for path in ALL_WORKFLOWS
        if re.search(r"(?m)^\s+[a-z-]+:\s*write-all\s*$", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"workflows granting write-all: {offenders}"


def test_no_workflow_uses_a_dangerous_trigger() -> None:
    """``pull_request_target`` and ``workflow_run`` run with a write token and
    access to secrets, so a fork's code must never be built by them."""
    offenders = [
        path.name
        for path in ALL_WORKFLOWS
        if re.search(
            r"(?m)^\s*(pull_request_target|workflow_run)\s*:",
            path.read_text(encoding="utf-8"),
        )
    ]
    assert not offenders, f"workflows with a dangerous trigger: {offenders}"
