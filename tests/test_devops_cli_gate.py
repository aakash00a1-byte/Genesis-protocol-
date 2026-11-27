"""R6-d: the devops skill managers must not run a command on their own.

``genesis_protocol/skills/devops`` called ``subprocess.run(["kubectl"] + args)``
directly, so ``KubernetesManager().run_command("delete", "ns", "prod")`` ran a
destructive cluster command with no owner check, no consent and no policy - one
argv, no shell metacharacter anywhere, so the earlier ``shell=False`` fix never
touched it. Every command now goes through ``run_guarded_command``.
"""

import asyncio
from pathlib import Path

import pytest

from genesis_protocol.agentic import policy as policy_module
from genesis_protocol.agentic.code_consent import get_code_consent
from genesis_protocol.skills import devops
from genesis_protocol.skills.devops import (
    CloudManager,
    DockerManager,
    KubernetesManager,
    execute_docker_list,
    execute_k8s_get_pods,
    run_guarded_command,
)
from genesis_protocol.tools.cli_policy import canonical_command

OWNER = 1
STRANGER = 999


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(OWNER))
    policy_module._default = None
    yield OWNER
    policy_module._default = None


@pytest.fixture
def consent(tmp_path, monkeypatch):
    monkeypatch.setenv("GLUTEN_CODE_CONSENT_FILE", str(tmp_path / "consent.json"))
    return get_code_consent()


# --- the guard itself -------------------------------------------------------

def test_a_harmless_command_runs_for_the_owner(owner):
    result = run_guarded_command("echo", ["hello"], user_id=OWNER)

    assert result["success"] is True
    assert result["stdout"].strip() == "hello"


def test_no_caller_identity_is_refused(owner):
    result = run_guarded_command("echo", ["hello"])

    assert result["success"] is False
    assert result["denied"] is True
    assert "owner" in result["error"]
    assert "stdout" not in result


def test_a_non_owner_is_refused(owner):
    result = run_guarded_command("echo", ["hello"], user_id=STRANGER)

    assert result["denied"] is True
    assert "not the owner" in result["error"]


@pytest.mark.parametrize("binary,args", [
    ("kubectl", ["delete", "ns", "prod"]),
    ("kubectl", ["apply", "-f", "prod.yaml"]),
    ("kubectl", ["exec", "-it", "pod", "--", "sh"]),
    ("docker", ["run", "--privileged", "alpine"]),
    ("docker", ["rm", "-f", "db"]),
    ("aws", ["s3", "rm", "s3://bucket", "--recursive"]),
    ("aws", ["iam", "create-user", "x"]),
    ("terraform", ["apply", "-auto-approve"]),
    ("gh", ["pr", "merge", "90"]),
    ("crontab", ["-r"]),
])
def test_destructive_commands_are_refused_for_the_owner_too(owner, binary, args):
    result = run_guarded_command(binary, args, user_id=OWNER, approval_id="forged")

    assert result["success"] is False
    assert result["denied"] is True
    assert "refused" in result["error"]


def test_a_credential_read_is_refused(owner):
    result = run_guarded_command("kubectl", ["describe", "secret", "db"], user_id=OWNER)

    assert result["denied"] is True


def test_a_state_changing_command_needs_an_approval(owner):
    result = run_guarded_command("printenv", ["PATH"], user_id=OWNER)

    assert result["denied"] is True
    assert "approval" in result["error"]


def test_an_approval_lets_one_exact_command_run_once(owner, consent):
    pending = consent.request(OWNER, canonical_command("printenv", ["PATH"]))

    first = run_guarded_command("printenv", ["PATH"], user_id=OWNER,
                                approval_id=pending.request_id)
    replay = run_guarded_command("printenv", ["PATH"], user_id=OWNER,
                                 approval_id=pending.request_id)

    assert first["success"] is True
    assert first["stdout"].strip(), "the approved command must actually have run"
    assert replay["denied"] is True
    assert "already used" in replay["error"]


def test_an_approval_does_not_cover_a_different_argument(owner, consent):
    pending = consent.request(OWNER, canonical_command("printenv", ["PATH"]))

    result = run_guarded_command("printenv", ["HOME"], user_id=OWNER,
                                 approval_id=pending.request_id)

    assert result["denied"] is True


# --- the managers delegate to the guard ------------------------------------

def test_docker_manager_refuses_removal(owner):
    manager = DockerManager(user_id=OWNER)
    manager.docker_available = True

    result = manager.run_command("rm", "-f", "db")

    assert result["denied"] is True


def test_kubernetes_manager_refuses_deletion_and_apply(owner):
    manager = KubernetesManager(user_id=OWNER)
    manager.kubectl_available = True

    assert manager.run_command("delete", "pod", "web").get("denied") is True
    assert manager.run_command("apply", "-f", "prod.yaml").get("denied") is True


def test_kubernetes_manager_refuses_without_an_owner():
    manager = KubernetesManager()
    manager.kubectl_available = True

    result = manager.run_command("get", "pods")

    assert result["denied"] is True
    assert "owner" in result["error"]


def test_cloud_manager_refuses_iam_and_s3_deletion(owner):
    manager = CloudManager(user_id=OWNER)
    manager.providers = {"aws": True, "gcp": True, "azure": True}

    assert manager.run_aws_command("iam", "create-user", "x").get("denied") is True
    assert manager.run_gcloud_command("projects", "delete", "p").get("denied") is True
    assert manager.run_az_command("group", "delete", "-n", "g").get("denied") is True


def test_a_non_owner_cannot_use_a_manager(owner):
    manager = DockerManager()
    manager.docker_available = True

    result = manager.run_command("ps", user_id=STRANGER)

    assert result["denied"] is True


# --- executors and probes ---------------------------------------------------

def test_the_executors_never_report_a_fabricated_success():
    listed = asyncio.run(execute_docker_list())
    pods = asyncio.run(execute_k8s_get_pods())

    assert listed["success"] is False
    assert pods["success"] is False
    assert "containers" not in listed and "pods" not in pods


def test_availability_probes_only_run_fixed_version_arguments():
    assert devops._probe("echo", ["--version"]) is True
    assert devops._probe("echo", ["rm", "-rf", "/"]) is False
    assert devops._probe("echo", ["delete"]) is False


def test_the_module_runs_no_command_outside_the_guard():
    source = Path(devops.__file__).read_text()

    assert "import subprocess" not in source, "every command goes through tools.cli_guard"
    assert "subprocess.run(" not in source
    assert "from genesis_protocol.tools.cli_guard import" in source
    assert "shell=True" not in source
