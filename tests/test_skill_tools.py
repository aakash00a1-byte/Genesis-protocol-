"""Tests for skill -> tool binding and the skill runner.

The gap these cover: skills declared tool names (``file_read``, ``subprocess``,
``docker`` ...) that resolved to nothing, so a skill could never run. These
assert that every declared name now resolves to a real tool, that a skill runs
through those tools with evidence, and that the policy still fails closed.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _all_declared_names():
    from genesis_protocol.skills import get_skill_registry

    names = set()
    for skill in get_skill_registry().list_all_skills():
        names.update(skill.tools or [])
    return names


def test_every_declared_tool_resolves_to_a_real_implementation():
    from genesis_protocol.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    missing = [n for n in _all_declared_names() if registry.get_tool(n) is None]
    assert missing == [], f"declared tools with no implementation: {missing}"


def test_declared_tools_report_a_permission_level():
    from genesis_protocol.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    for name in _all_declared_names():
        tool = registry.get_tool(name)
        perm = getattr(getattr(tool, "permission", None), "value", None)
        assert perm in {"safe", "restricted", "admin"}, (name, perm)


def test_tools_for_skill_returns_only_runnable_names():
    from genesis_protocol.tools.skill_tools import tools_for_skill

    runnable = tools_for_skill("web_search")
    assert set(runnable) == {"tavily", "http"}


def test_unavailable_cli_tool_fails_honestly():
    from genesis_protocol.tools.skill_tools import _cli

    # A binary that is guaranteed absent: the tool must say so rather than
    # pretend to have run. (Checking a real CLI like kubectl is
    # environment-dependent - CI runners ship several of them.)
    missing = _cli("absent_cli", "definitely-not-a-real-binary-xyz")()
    result = missing.execute(args="get pods")
    assert result["success"] is False
    assert "not installed" in result["error"]


def test_installed_cli_tool_reports_a_nonzero_exit():
    from genesis_protocol.tools.skill_tools import _cli

    tool = _cli("sh_cli", "sh")()
    result = tool.execute(args='-c "exit 3"')
    assert result["success"] is False
    assert result["returncode"] == 3


def test_runner_executes_a_safe_tool_and_skips_unused_ones():
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.skills import SkillRunner

    runner = SkillRunner(policy=AgentPolicy(owner_ids={1}))
    # notion_integration declares http + json; only json is given parameters.
    out = runner.run(
        1,
        "notion_integration",
        {"json": {"action": "parse", "text": '{"a": 1}'}},
        owner_approved=True,
    )
    steps = {s["tool"]: s for s in out["steps"]}
    assert steps["json"]["ran"] is True
    assert steps["json"]["result"]["data"] == {"a": 1}
    assert steps["http"]["ran"] is False
    assert out["executed"] is True
    # The skill did not fully run (one declared tool had no parameters).
    assert out["success"] is False


def test_runner_denies_restricted_tool_for_non_owner():
    from genesis_protocol.agentic.policy import AgentPolicy
    from genesis_protocol.agentic.skills import SkillRunner

    runner = SkillRunner(policy=AgentPolicy(owner_ids={1}))
    out = runner.run(2, "web_search", {"http": {"url": "https://example.com"}})
    step = {s["tool"]: s for s in out["steps"]}["http"]
    assert step["denied"] is True
    assert step["ran"] is False
    assert "not the owner" in step["error"]


def test_runner_reports_unknown_skill():
    from genesis_protocol.agentic.skills import SkillRunner

    out = SkillRunner().run(1, "not_a_real_skill", {})
    assert out["success"] is False
    assert "unknown skill" in out["error"]


def test_git_tool_refuses_non_readonly_operations():
    from genesis_protocol.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute("git", {"operation": "push"})
    assert result["success"] is False
    assert "read-only" in result["error"]


def test_subprocess_tool_refuses_privileged_commands():
    from genesis_protocol.tools.tool_registry import get_tool_registry

    registry = get_tool_registry()
    result = registry.execute("subprocess", {"command": "git push origin main"})
    assert result["success"] is False
    assert "refused" in result["error"]


def test_agent_loop_runs_a_skill_step():
    from genesis_protocol.agentic.agent_loop import AgentLoop
    from genesis_protocol.agentic.policy import AgentPolicy

    loop = AgentLoop(policy=AgentPolicy(owner_ids={1}))
    result = loop.run(
        1,
        goal="parse some json",
        steps=[
            {
                "type": "skill",
                "skill": "notion_integration",
                "tool_params": {"json": {"action": "parse", "text": "[1, 2]"}},
            }
        ],
        owner_approved=True,
    )
    step = result["steps"][0]
    assert step["type"] == "skill"
    assert step["executed"] is True
