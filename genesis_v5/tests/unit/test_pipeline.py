"""Tests for the authority pipeline: generation is free, action is governed."""
from __future__ import annotations

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.pipeline.authority import AuthorityPipeline, Stage
from genesis.tools.gateway import ToolRequest


def _pipeline() -> AuthorityPipeline:
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    return AuthorityPipeline(ParallelGenerator(seed=1), kernel.gateway)


def test_propose_has_no_side_effects() -> None:
    result = _pipeline().propose("design a cache", shots=64)
    assert result.stages == [Stage.GENERATE.value]
    assert result.executed == 0
    assert result.denied == 0


def test_bypass_is_never_available() -> None:
    result = _pipeline().propose("anything", shots=64)
    assert result.bypass_available is False
    assert result.to_dict()["bypass_available"] is False


def test_denied_tool_is_recorded_with_a_reason() -> None:
    pipeline = _pipeline()
    request = ToolRequest(
        tool="file.write",
        args={"path": "/workspace/nope.txt", "content": "x"},
        actor="demo",
        role="researcher",
        cwd="/workspace",
    )
    result = pipeline.submit("write something", [request], shots=64)
    assert result.denied == 1
    assert result.executed == 0
    assert result.actions[0].reason
    assert result.actions[0].status == "denied"


def test_granted_tool_runs_and_is_counted() -> None:
    pipeline = _pipeline()
    request = ToolRequest(
        tool="file.list",
        args={"path": "/workspace"},
        actor="demo",
        role="coder",
        cwd="/workspace",
    )
    result = pipeline.submit("list files", [request], shots=64)
    assert result.executed == 1
    assert Stage.EXECUTE.value in result.stages


def test_denied_request_does_not_execute() -> None:
    pipeline = _pipeline()
    request = ToolRequest(
        tool="file.write",
        args={"path": "/workspace/pipeline_should_not_exist.txt", "content": "x"},
        actor="demo",
        role="researcher",
        cwd="/workspace",
    )
    pipeline.submit("write", [request], shots=64)
    from pathlib import Path

    assert not Path("/workspace/pipeline_should_not_exist.txt").exists()
