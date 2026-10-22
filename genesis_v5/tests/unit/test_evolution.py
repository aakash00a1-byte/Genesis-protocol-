"""Phase 18 — Evolution agent (self-observation and self-proposal).

Covers: signal collection from the real ledgers/metrics, proposal generation
and ranking, deduplication, bounds, the review/authority invariants, the
verdict rule, persistence, and the end-to-end path through the Kernel
pipeline. No mocks of the gate: the agent is exercised against real ledgers.
"""
from __future__ import annotations

import json

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.evolution.evolution import (
    EvolutionAgent,
    EvolutionConfig,
    ProposalStore,
)
from genesis.evolution.signals import (
    HealthSignal,
    ImprovementSignal,
    SignalCollector,
    WeaknessSignal,
    summarize,
)
from genesis.kernel.kernel import KernelRequest
from genesis.transparency.ledger import TransparencyReport


# ------------------------------------------------------------------
# Signal collection
# ------------------------------------------------------------------
def test_collector_reads_failure_ledger() -> None:
    report = TransparencyReport()
    report.failures.record(
        component="relay.market",
        what="ticker sign inverted",
        why="label computed before sign",
        impact="wrong mover shown",
    )
    collector = SignalCollector(failure_ledger=report.failures)
    weaknesses = collector.weaknesses()
    assert len(weaknesses) == 1
    assert weaknesses[0].component == "relay.market"
    assert weaknesses[0].severity == "medium"


def test_collector_flags_security_failures_high() -> None:
    report = TransparencyReport()
    report.failures.record(
        component="gateway",
        what="credential leaked in log",
        why="redaction disabled",
        impact="security exposure",
    )
    collector = SignalCollector(failure_ledger=report.failures)
    assert collector.weaknesses()[0].severity == "high"
    assert collector.weaknesses()[0].blocking is True


def test_collector_health_signal_on_denial_rate() -> None:
    from genesis.monitoring.metrics import Metrics

    metrics = Metrics()
    for _ in range(10):
        metrics.incr("kernel.agent_tool_requests")
    for _ in range(4):
        metrics.incr("kernel.agent_tool_denied")
    collector = SignalCollector(metrics=metrics, denial_rate_threshold=0.2)
    health = collector.health()
    assert health and health[0].metric == "agent_tool_denial_rate"
    assert health[0].value == 0.4


def test_collector_opportunity_from_repeated_weakness() -> None:
    report = TransparencyReport()
    for _ in range(2):
        report.failures.record(
            component="planner",
            what="empty plan",
            why="no steps",
            impact="nothing ran",
        )
    collector = SignalCollector(failure_ledger=report.failures)
    opportunities = collector.opportunities()
    assert len(opportunities) == 1
    assert "planner" in opportunities[0].opportunity


def test_summarize_counts_by_kind() -> None:
    signals = [
        WeaknessSignal(component="a", what="x"),
        HealthSignal(metric="m", value=1.0, expectation="0"),
        ImprovementSignal(area="a", opportunity="o"),
    ]
    assert summarize(signals) == {"weakness": 1, "health": 1, "improvement": 1}


# ------------------------------------------------------------------
# Proposals
# ------------------------------------------------------------------
def _agent_with_signals(*signals) -> EvolutionAgent:
    return EvolutionAgent(
        config=EvolutionConfig(enabled=True, persist=False),
        collector=SignalCollector(),
        store=None,
    )


def test_agent_proposes_from_explicit_signals() -> None:
    from genesis.agents.base import AgentTask

    agent = _agent_with_signals()
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={
            "signals": [
                {"kind": "weakness", "component": "relay", "what": "sign bug",
                 "severity": "high", "impact": "wrong mover"},
                {"kind": "health", "metric": "denial_rate", "value": 0.5,
                 "expectation": "<0.2", "severity": "medium"},
            ]
        },
    )
    result = agent.run(task)
    assert result.ok
    proposals = result.output["proposals"]
    assert len(proposals) == 2
    # The high-severity fix outranks the health investigation.
    assert proposals[0]["kind"] == "fix"
    assert proposals[0]["priority"] > proposals[1]["priority"]


def test_every_proposal_requires_review_and_authority() -> None:
    from genesis.agents.base import AgentTask

    agent = _agent_with_signals()
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={"signals": [{"kind": "weakness", "component": "c", "what": "w"}]},
    )
    report = agent.run(task).output
    assert report["requires_review"] is True
    assert report["bypass_available"] is False
    for proposal in report["proposals"]:
        assert proposal["requires_review"] is True
        assert proposal["requires_authority"] is True
        assert proposal["status"] == "proposed"


def test_duplicate_signals_deduplicate_with_raised_priority() -> None:
    from genesis.agents.base import AgentTask

    agent = _agent_with_signals()
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={
            "signals": [
                {"kind": "weakness", "component": "c", "what": "same", "severity": "low"},
                {"kind": "weakness", "component": "c", "what": "same", "severity": "low"},
            ]
        },
    )
    proposals = agent.run(task).output["proposals"]
    assert len(proposals) == 1
    # Dedup raises priority above a single low-severity proposal (0.3).
    assert proposals[0]["priority"] > 0.3


def test_max_proposals_bound_is_enforced() -> None:
    from genesis.agents.base import AgentTask

    agent = EvolutionAgent(
        config=EvolutionConfig(enabled=True, persist=False, max_proposals=2),
        collector=SignalCollector(),
    )
    signals = [
        {"kind": "weakness", "component": f"c{i}", "what": f"w{i}"} for i in range(6)
    ]
    task = AgentTask(agent="evolution", instruction="observe", metadata={"signals": signals})
    report = agent.run(task).output
    assert len(report["proposals"]) == 2
    assert any("deferred" in note for note in report["notes"])


def test_blocking_signal_sets_attention_required() -> None:
    from genesis.agents.base import AgentTask

    agent = _agent_with_signals()
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={
            "signals": [
                {"kind": "weakness", "component": "sec", "what": "breach",
                 "impact": "security", "severity": "critical"},
            ]
        },
    )
    report = agent.run(task).output
    assert report["verdict"] == "attention_required"
    assert report["ok"] is False


def test_all_clear_when_no_signals() -> None:
    agent = EvolutionAgent(
        config=EvolutionConfig(enabled=True, persist=False),
        collector=SignalCollector(),
    )
    report = agent.observe()
    assert report.verdict == "all_clear"
    assert report.proposals == []
    assert report.ok is True


def test_agent_has_no_tool_gateway_by_default() -> None:
    import pytest

    agent = _agent_with_signals()
    with pytest.raises(PermissionError):
        agent.request_tool("file.write", {"path": "/etc/passwd", "content": "x"})


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------
def test_proposal_store_roundtrip(tmp_path) -> None:
    from genesis.agents.base import AgentTask

    store = ProposalStore(str(tmp_path))
    agent = EvolutionAgent(
        config=EvolutionConfig(enabled=True, persist=True, store_dir=str(tmp_path)),
        collector=SignalCollector(),
        store=store,
    )
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={"signals": [{"kind": "weakness", "component": "c", "what": "w"}]},
    )
    agent.run(task)
    records = store.load()
    assert len(records) == 1
    assert records[0]["proposals"]


def test_proposal_store_tolerates_corrupt_line(tmp_path) -> None:
    store = ProposalStore(str(tmp_path))
    store.append(_empty_report())
    with open(store.path, "a", encoding="utf-8") as fh:
        fh.write("not json\n")
    store.append(_empty_report())
    assert len(store.load()) == 2


def _empty_report():
    from genesis.evolution.evolution import EvolutionReport

    return EvolutionReport(cycle_id="cycle-test")


# ------------------------------------------------------------------
# Wiring + pipeline
# ------------------------------------------------------------------
def test_bootstrap_wires_evolution_when_enabled() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    cfg.evolution.enabled = True
    cfg.evolution.persist = False
    kernel = build(cfg)
    assert kernel.evolution is not None
    assert kernel.evolution.collector is not None


def test_evolution_disabled_by_default() -> None:
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    assert kernel.evolution is None


def test_planner_routes_self_improve_task_to_evolution_agent() -> None:
    from genesis.planning.planner import Planner

    plan = Planner().plan("self-improve: propose an improvement for the relay")
    agents = {step.agent for step in plan.steps}
    assert "evolution" in agents


def test_ordinary_task_does_not_invoke_evolution_agent() -> None:
    from genesis.planning.planner import Planner

    plan = Planner().plan("implement a cache and verify it")
    agents = {step.agent for step in plan.steps}
    assert "evolution" not in agents


def test_kernel_pipeline_runs_evolution_agent_end_to_end() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    cfg.evolution.enabled = True
    cfg.evolution.persist = False
    kernel = build(cfg)
    response = kernel.run(
        KernelRequest(
            task="self-improve: observe the system and propose improvements",
            actor="operator",
            role="admin",
        )
    )
    assert response.ok, response.errors
    assert response.result
    assert response.qa is not None


# ------------------------------------------------------------------
# Direct end-to-end: real ledgers -> proposals
# ------------------------------------------------------------------
def test_end_to_end_from_real_failures_to_proposals() -> None:
    cfg = GenesisConfig(env=Env.TESTING, offline=True)
    cfg.evolution.enabled = True
    cfg.evolution.persist = False
    kernel = build(cfg)
    assert kernel.evolution is not None

    kernel.transparency.failures.record(
        component="relay.market",
        what="sign inverted",
        why="labelled before sign",
        impact="wrong mover",
    )
    report = kernel.evolution.observe()
    assert report.counts["weakness"] == 1
    assert report.proposals
    assert report.proposals[0].kind == "fix"
    # A JSON-serialisable report is part of the contract.
    json.dumps(report.to_dict())


def test_evolution_agent_result_is_json_safe() -> None:
    from genesis.agents.base import AgentTask

    agent = _agent_with_signals()
    task = AgentTask(
        agent="evolution",
        instruction="observe",
        metadata={"signals": [{"kind": "improvement", "area": "docs",
                               "opportunity": "add examples"}]},
    )
    result = agent.run(task)
    json.dumps(result.to_dict())
    assert result.metadata["verdict"] == "all_clear"
