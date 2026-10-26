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


def test_heartbeat_runs_on_a_daily_schedule() -> None:
    """Regression: the daily heartbeat did not exist.

    It relied on an in-run interval (RELAY_HEARTBEAT_HOURS=24) inside a run that
    lasts only 5h30m, so the interval never elapsed, and heartbeat.yml had no
    cron either. A daily schedule must exist somewhere.
    """
    text = HEARTBEAT.read_text(encoding="utf-8")
    match = re.search(r"^on:\n(?:.*\n)*?\s*- cron:\s*'([^']+)'", text, re.M)
    assert match, "heartbeat.yml must declare a schedule cron"
    minute, hour, dom, month, dow = match.group(1).split()
    assert dom == "*" and month == "*" and dow == "*", "must be a daily cron"
    assert hour != "*", "must run once a day, not hourly"


def test_keepalive_does_not_claim_an_unreachable_heartbeat() -> None:
    """The in-run heartbeat interval must not exceed the run length."""
    text = KEEPALIVE.read_text(encoding="utf-8")

    def _env(name: str) -> float:
        m = re.search(rf"{name}:\s*\"([0-9.]+)\"", text)
        assert m, f"{name} must be set explicitly"
        return float(m.group(1))

    run_seconds = _env("RELAY_RUN_SECONDS")
    heartbeat_hours = _env("RELAY_HEARTBEAT_HOURS")
    if heartbeat_hours > 0:
        assert heartbeat_hours * 3600 < run_seconds, (
            "an in-run heartbeat interval that cannot elapse inside one run "
            "silently sends nothing"
        )


def test_ci_can_be_dispatched_by_name() -> None:
    """Regression: agent PRs showed no CI checks.

    The harness opens PRs with the default GITHUB_TOKEN, whose events GitHub
    suppresses, so `on: pull_request` never fires for them. `workflow_dispatch`
    is the documented exception that always creates a run, so ci.yml must accept
    it and the harness must be able to name it.
    """
    ci = WORKFLOWS / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    assert re.search(r"^on:", text, re.M)
    assert re.search(r"^\s{2}workflow_dispatch:", text, re.M), (
        "ci.yml must accept workflow_dispatch, or an agent PR can never get checks"
    )
    # The pull_request trigger must stay for human PRs.
    assert re.search(r"^\s{2}pull_request:", text, re.M)


def test_self_improve_can_dispatch_ci_and_deploy() -> None:
    """The harness needs actions:write and both workflow names."""
    text = (WORKFLOWS / "self-improve.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s{2}actions:\s*write", text, re.M)
    script = (WORKFLOWS.parent.parent / "scripts" / "self_improve.py").read_text(encoding="utf-8")
    assert '"ci.yml"' in script
    assert '"deploy-space.yml"' in script
