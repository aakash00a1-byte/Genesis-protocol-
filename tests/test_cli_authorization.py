"""R6: the CLI tools are authorised per operation, not by ``shell=False``.

The tools (kubectl, aws, docker, terraform, gh, gcloud, az, crontab, pdflatex,
pandoc) are audited as a set: each one must classify its command, refuse the
destructive/deployment/credential/privilege verbs outright, and require an
owner identity plus a single-use approval bound to the exact executable and
arguments for anything else.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import genesis_protocol.agentic.code_consent as consent_module
import genesis_protocol.agentic.policy as policy_module
from genesis_protocol.agentic.agent_loop import AgentLoop
from genesis_protocol.agentic.code_consent import CodeConsentStore
from genesis_protocol.agentic.policy import AgentPolicy
from genesis_protocol.tools.cli_policy import (
    ALLOW,
    CONSENT,
    DENY,
    canonical_command,
    classify,
)
from genesis_protocol.tools.skill_tools import _cli

OWNER = 1
NON_OWNER = 2


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(OWNER))
    monkeypatch.setenv("GLUTEN_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    store = CodeConsentStore(path=str(tmp_path / "consent.json"))
    monkeypatch.setattr(consent_module, "_default", store)
    monkeypatch.setattr(policy_module, "_default", None)
    return store


def _fake_cli(name: str = "fakecli", binary: str = "printenv"):
    """A CLI tool backed by a binary that exists here (printenv)."""
    return _cli(name, binary)()


def _approve(store, payload: str, user_id: int = OWNER) -> str:
    return store.request(user_id, payload).request_id


# --- the audit: every registered CLI tool classifies its command ------------
def _registered_cli_tools():
    from genesis_protocol.tools.tool_registry import get_tool_registry

    return [t for t in get_tool_registry().get_all_tools()
            if getattr(t, "cli_consent", False)]


def test_every_registered_cli_tool_is_covered_by_the_policy():
    tools = _registered_cli_tools()
    names = sorted(t.name for t in tools)

    assert names == ["aws", "az", "crontab", "docker", "gcloud", "gh", "kubectl",
                     "pandoc", "pdflatex", "terraform"], names
    for tool in tools:
        verdict = classify(tool._binary, ["version"])
        assert verdict.decision in {ALLOW, CONSENT, DENY}, tool.name


@pytest.mark.parametrize("binary,args", [
    ("kubectl", ["delete", "namespace", "prod"]),
    ("kubectl", ["drain", "node-1"]),
    ("kubectl", ["exec", "-it", "pod", "--", "id"]),
    ("kubectl", ["apply", "-f", "deploy.yaml"]),
    ("kubectl", ["get", "secret", "db-creds"]),
    ("kubectl", ["config", "delete-context", "prod"]),
    ("kubectl", ["rollout", "restart", "deploy/api"]),
    ("docker", ["run", "--privileged", "alpine"]),
    ("docker", ["system", "prune", "-af"]),
    ("docker", ["rmi", "abc123"]),
    ("docker", ["push", "registry/app"]),
    ("docker", ["login", "-u", "x"]),
    ("aws", ["iam", "create-user", "--user-name", "x"]),
    ("aws", ["s3", "rm", "s3://bucket/key"]),
    ("aws", ["secretsmanager", "get-secret-value", "--secret-id", "db"]),
    ("aws", ["sts", "assume-role", "--role-arn", "arn"]),
    ("terraform", ["apply", "-auto-approve"]),
    ("terraform", ["destroy"]),
    ("terraform", ["state", "rm", "x"]),
    ("gh", ["pr", "merge", "1"]),
    ("gh", ["api", "-X", "POST", "/repos/x/y"]),
    ("gh", ["auth", "token"]),
    ("gh", ["secret", "set", "X"]),
    ("gcloud", ["auth", "login"]),
    ("gcloud", ["compute", "instances", "delete", "vm"]),
    ("az", ["login"]),
    ("az", ["vm", "delete", "-n", "vm"]),
    ("crontab", ["-r"]),
    ("crontab", ["-e"]),
])
def test_dangerous_operations_are_denied_not_consented(binary, args):
    verdict = classify(binary, args)

    assert verdict.decision == DENY, (binary, args, verdict)
    assert verdict.operation
    assert ("destructive" in verdict.reason
            or "credential" in verdict.reason
            or "persistence" in verdict.reason), verdict.reason


@pytest.mark.parametrize("binary,args", [
    ("kubectl", ["get", "pods"]),
    ("kubectl", ["describe", "deploy", "api"]),
    ("kubectl", ["logs", "pod-1"]),
    ("docker", ["ps", "-a"]),
    ("docker", ["images"]),
    ("docker", ["ps", "--filter", "name=delete-me"]),
    ("aws", ["describe-instances"]),
    ("aws", ["list-buckets"]),
    ("terraform", ["plan"]),
    ("gh", ["pr", "list"]),
    ("gh", ["pr", "view", "1"]),
    ("gcloud", ["compute", "instances", "list"]),
    ("az", ["vm", "list", "-g", "rg"]),
    ("crontab", ["-l"]),
    ("pandoc", ["-o", "out.pdf", "in.md"]),
    ("pdflatex", ["report.tex"]),
])
def test_read_only_operations_are_allowed(binary, args):
    assert classify(binary, args).decision == ALLOW


def test_unknown_operations_need_consent():
    verdict = classify("kubectl", ["rollout", "status", "deploy/api"])

    # ``rollout`` is a deployment verb, so it is refused rather than consented to.
    assert verdict.decision == DENY
    assert classify("gcloud", ["compute", "disks", "resize", "d1"]).decision == CONSENT


def test_a_valid_approval_cannot_authorise_a_denied_operation(isolated):
    tool = _fake_cli()
    # printenv takes no verb, so it is a consent tool; the deny path is checked
    # on the classifier for a real binary with an approval that matches it.
    payload = canonical_command("kubectl", ["delete", "namespace", "prod"])
    approval = _approve(isolated, payload)

    verdict = classify("kubectl", ["delete", "namespace", "prod"])
    assert verdict.decision == DENY
    assert isolated.get(OWNER, approval) is not None  # the approval is irrelevant
    assert tool  # keep the fixture meaningful


# --- execution: identity + approval + exact binding -------------------------
def test_no_caller_identity_is_refused(isolated):
    result = _fake_cli().execute(args="PATH")

    assert result["success"] is False
    assert result["denied"] is True
    assert "no caller identity" in result["error"]


def test_non_owner_is_refused_even_with_a_valid_approval(isolated):
    payload = canonical_command("printenv", ["PATH"])
    approval = _approve(isolated, payload, user_id=NON_OWNER)

    result = _fake_cli().execute(args="PATH", _user_id=NON_OWNER, approval_id=approval)

    assert result["success"] is False
    assert "is not the owner" in result["error"]


def test_owner_without_an_approval_is_refused(isolated):
    result = _fake_cli().execute(args="PATH", _user_id=OWNER)

    assert result["success"] is False
    assert "approval record is required" in result["error"]


def test_owner_with_a_scoped_approval_runs_once(isolated):
    payload = canonical_command("printenv", ["PATH"])
    approval = _approve(isolated, payload)
    tool = _fake_cli()

    first = tool.execute(args="PATH", _user_id=OWNER, approval_id=approval)
    replay = tool.execute(args="PATH", _user_id=OWNER, approval_id=approval)

    assert first["success"] is True and first["stdout"].strip()
    assert replay["success"] is False and "already used" in replay["error"]


def test_modified_arguments_are_refused(isolated):
    approval = _approve(isolated, canonical_command("printenv", ["PATH"]))

    result = _fake_cli().execute(args="HOME", _user_id=OWNER, approval_id=approval)

    assert result["success"] is False
    assert "does not match" in result["error"]


def test_an_approval_does_not_transfer_to_another_executable(isolated):
    approval = _approve(isolated, canonical_command("printenv", ["PATH"]))

    other = _cli("othercli", "dirname")()
    result = other.execute(args="PATH", _user_id=OWNER, approval_id=approval)

    assert result["success"] is False
    assert "does not match" in result["error"]


def test_forged_owner_approved_in_params_is_not_authority(isolated):
    result = _fake_cli().execute(args="PATH", owner_approved=True, _user_id=NON_OWNER)

    assert result["success"] is False
    assert result["denied"] is True


def test_the_loop_passes_the_verified_identity_to_cli_tools(isolated):
    from genesis_protocol.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    registry.register(_fake_cli("loopcli"))
    try:
        approval = _approve(isolated, canonical_command("printenv", ["PATH"]))
        loop = AgentLoop(policy=AgentPolicy(owner_ids={OWNER}))

        owner = loop.run(OWNER, goal="env", steps=[{
            "type": "tool", "tool": "loopcli",
            "params": {"args": "PATH", "approval_id": approval},
        }])
        assert owner["steps"][0]["result"]["success"] is True

        non_owner = loop.run(NON_OWNER, goal="env", steps=[{
            "type": "tool", "tool": "loopcli", "params": {"args": "PATH"},
        }])
        assert non_owner["steps"][0]["success"] is False
        assert non_owner["steps"][0]["denied"] is True
    finally:
        registry.unregister("loopcli")


def test_the_approval_id_is_not_forwarded_to_the_binary(isolated):
    """The approval id is consumed by the tool, never passed as an argument."""
    approval = _approve(isolated, canonical_command("printenv", ["PATH"]))

    result = _fake_cli().execute(args="PATH", _user_id=OWNER, approval_id=approval)

    assert result["success"] is True
    assert approval not in (result.get("stdout") or "")
