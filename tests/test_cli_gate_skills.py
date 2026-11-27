"""Every skill that shells out goes through the one CLI gate.

The devops managers were the first finding (R6-d), but the same pattern sat in
four more modules: ``automation`` installed a crontab, ``file_management`` ran
arbitrary ``git``, ``specialized`` ran arbitrary ``gh`` and ``coding`` ran a
program. Each built its own argv, so ``shell=False`` never applied. All of them
now call ``tools.cli_guard.run_guarded_command``, and the static audit at the
bottom keeps it that way.
"""

import ast
from pathlib import Path

import pytest

from genesis_protocol.agentic import policy as policy_module
from genesis_protocol.skills.automation import CronManager
from genesis_protocol.skills.coding import Debugger
from genesis_protocol.skills.document import LaTeXDocument, MarkdownToPDF
from genesis_protocol.skills.file_management import GitOperations
from genesis_protocol.skills.specialized import GitHubPRManager
from genesis_protocol.tools.cli_guard import probe, run_guarded_command
from genesis_protocol.tools.cli_policy import classify

OWNER = 1
STRANGER = 999

# The only modules allowed to start a process: the gate itself, the canonical
# tool layer (which calls the gate), and the code sandbox.
PROCESS_ALLOWED = {
    "tools/cli_guard.py",
    "tools/skill_tools.py",
    "agentic/sandbox.py",
}


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.setenv("GLUTEN_OWNER_IDS", str(OWNER))
    policy_module._default = None
    yield OWNER
    policy_module._default = None


# --- crontab: installing is persistence, refused outright -------------------

def test_crontab_install_is_never_consentable():
    verdict = classify("crontab", ["/tmp/crontab.txt"])

    assert verdict.denied is True
    assert "persistence" in verdict.reason


def test_crontab_install_is_refused_even_with_an_approval(owner):
    result = run_guarded_command("crontab", ["/tmp/crontab.txt"], user_id=OWNER,
                                 approval_id="anything")

    assert result["success"] is False
    assert result["denied"] is True


def test_crontab_listing_needs_the_owner():
    assert classify("crontab", ["-l"]).decision == "allow"
    assert run_guarded_command("crontab", ["-l"])["denied"] is True


def test_cron_manager_refuses_without_an_identity():
    result = CronManager().create_job("0 3 * * *", "echo hi")

    assert result["success"] is False
    assert result["denied"] is True


# --- git -------------------------------------------------------------------

@pytest.mark.parametrize("args", [
    ["status"], ["log", "--oneline"], ["diff"], ["show", "HEAD"],
])
def test_git_reads_are_allowed(args):
    assert classify("git", args).decision == "allow"


@pytest.mark.parametrize("args", [
    ["push", "origin", "main"],
    ["reset", "--hard"],
    ["commit", "-m", "x"],
    ["checkout", "main"],
    ["branch", "-D", "main"],
    ["clean", "-fdx"],
    ["rebase", "main"],
])
def test_git_state_changes_are_refused(args):
    assert classify("git", args).denied is True


def test_a_label_value_is_not_read_as_a_git_verb():
    assert classify("kubectl", ["get", "pods", "-l", "branch=main"]).decision == "allow"


def test_git_operations_run_reads_for_the_owner(owner):
    result = GitOperations(".", user_id=OWNER).run_git("status", "--porcelain")

    assert result.get("denied") is not True
    assert "returncode" in result


def test_git_operations_refuse_without_an_identity():
    result = GitOperations(".").run_git("status")

    assert result["denied"] is True


def test_git_operations_refuse_a_push_for_the_owner(owner):
    result = GitOperations(".", user_id=OWNER).run_git("push", "origin", "main")

    assert result["denied"] is True
    assert "push" in result["error"]


def test_the_git_helpers_keep_their_read_behaviour(owner):
    git = GitOperations(".", user_id=OWNER)

    assert git.get_status()["success"] is True
    assert git.get_current_branch().strip() != ""
    assert isinstance(git.get_branches(), list)
    assert isinstance(git.get_log(1), list)


def test_the_git_write_helpers_are_refused(owner):
    git = GitOperations(".", user_id=OWNER)

    for call in (lambda: git.commit("x"), lambda: git.push(),
                 lambda: git.pull(), lambda: git.merge("main")):
        assert call()["denied"] is True


def test_git_operations_refuse_a_non_owner(owner):
    result = GitOperations(".", user_id=STRANGER).run_git("status")

    assert result["denied"] is True


# --- gh --------------------------------------------------------------------

def test_gh_reads_are_allowed_and_merge_is_refused():
    assert classify("gh", ["pr", "view", "90"]).decision == "allow"
    assert classify("gh", ["pr", "merge", "90"]).denied is True
    assert classify("gh", ["api", "repos/x"]).denied is True


def test_the_pr_manager_refuses_a_merge(owner):
    result = GitHubPRManager(".", user_id=OWNER).run_gh("pr", "merge", "90")

    assert result["denied"] is True


def test_the_pr_manager_refuses_without_an_identity():
    assert GitHubPRManager(".").run_gh("pr", "list")["denied"] is True


# --- coding and documents --------------------------------------------------

def test_the_debugger_needs_an_identity_and_an_approval(owner):
    anonymous = Debugger().run_tests()
    unapproved = Debugger(user_id=OWNER).run_tests()

    assert anonymous["denied"] is True
    assert unapproved["denied"] is True
    assert "approval" in unapproved["error"]


def test_the_linter_needs_an_approval_too(owner):
    result = Debugger(user_id=OWNER).lint_code("genesis_protocol/tools/cli_policy.py")

    assert result["denied"] is True
    assert "approval" in result["error"]


def test_document_compilers_are_owner_only():
    assert LaTeXDocument()._check_latex() in (True, False)
    assert MarkdownToPDF()._check_pandoc() in (True, False)
    # The probes accept fixed version arguments only.
    assert probe("pdflatex", ["-interaction=nonstopmode", "x.tex"]) is False
    assert probe("pandoc", ["-o", "out.pdf"]) is False


# --- the static audit ------------------------------------------------------

PROCESS_CALLS = {
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output",
    "os.system", "os.popen", "os.execv", "os.spawnv",
    "asyncio.create_subprocess_exec", "asyncio.create_subprocess_shell",
}


def _process_calls(source: str):
    """Actual call sites, not string literals such as a red-flag pattern."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        parts, cur = [], node.func
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        name = ".".join(reversed(parts))
        if name in PROCESS_CALLS:
            hits.append((node.lineno, name))
    return hits


def test_no_product_module_starts_a_process_outside_the_gate():
    root = Path(__file__).resolve().parents[1] / "genesis_protocol"
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in PROCESS_ALLOWED:
            continue
        for lineno, name in _process_calls(path.read_text()):
            offenders.append(f"{rel}:{lineno} {name}")

    assert offenders == [], (
        "route these through genesis_protocol.tools.cli_guard: " + ", ".join(offenders))
