"""EvolutionAgent: Genesis observes itself and proposes its own improvements.

This is the self-improvement half of the V6 roadmap, built to the same rule as
everything else: **generation is free, execution is governed**.

The agent:

1. **Observes** — collects signals from the transparency ledgers and metrics
   (recent failures, denials, unresolved decisions). Read-only.
2. **Proposes** — turns each signal into a small, ranked, review-gated
   ``EvolutionProposal``. A proposal is text; it changes nothing.
3. **Records** — returns an ``EvolutionReport``. The caller (the harness, a
   human, or a scheduler) decides what, if anything, happens next.

It never edits code, never deploys, never merges, and never executes a tool on
its own. It is an ``Agent`` like any other, so when a Kernel-mediated gateway
is bound its tool requests would travel the same authority gate — but the
agent does not need one to do its job.

The backlog is bounded and de-duplicated: the same failure twice is one
proposal with a raised priority, not two proposals.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from genesis.agents.base import Agent, AgentResult, AgentState, AgentTask
from genesis.core import new_id, now_ms

from .signals import (
    HealthSignal,
    ImprovementSignal,
    SignalCollector,
    WeaknessSignal,
    summarize,
)

# How much each weakness severity contributes to a proposal's priority.
_SEVERITY_WEIGHT = {"low": 0.3, "medium": 0.5, "high": 0.75, "critical": 1.0}


@dataclass
class EvolutionConfig:
    """Bounds and switches for the evolution agent. Off by default."""

    enabled: bool = False
    # A cycle never produces more than this many proposals.
    max_proposals: int = 5
    # Proposals below this priority are dropped (not hidden — see report.notes).
    min_priority: float = 0.0
    # Where the proposal backlog is written when a store is attached.
    store_dir: str = "./data/evolution"
    persist: bool = True
    # The agent proposes as a low-privilege actor; it has no write authority.
    actor: str = "evolution"
    role: str = "viewer"


@dataclass
class EvolutionProposal:
    """One proposed improvement. Text only — it acts on nothing."""

    title: str
    area: str
    kind: str  # fix | investigate | improve
    rationale: str = ""
    evidence: list[str] = field(default_factory=list)
    priority: float = 0.5
    severity: str = "medium"
    source_signal_id: str = ""
    generated_frame: str = ""
    proposal_id: str = field(default_factory=lambda: new_id("evo"))
    status: str = "proposed"
    requires_review: bool = True
    requires_authority: bool = True
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "title": self.title,
            "area": self.area,
            "kind": self.kind,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "priority": round(self.priority, 4),
            "severity": self.severity,
            "source_signal_id": self.source_signal_id,
            "generated_frame": self.generated_frame,
            "status": self.status,
            "requires_review": self.requires_review,
            "requires_authority": self.requires_authority,
            "ts_ms": self.ts_ms,
        }


@dataclass
class EvolutionReport:
    """The full outcome of one self-observation cycle."""

    cycle_id: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[EvolutionProposal] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    verdict: str = "all_clear"
    notes: list[str] = field(default_factory=list)
    ts_ms: int = field(default_factory=now_ms)
    # A proposal can never opt out of review or the authority layer.
    bypass_available: bool = False

    @property
    def ok(self) -> bool:
        """True when nothing blocking was found. Proposals may still exist."""
        return self.verdict == "all_clear"

    def rank(self) -> list[EvolutionProposal]:
        return sorted(self.proposals, key=lambda p: (-p.priority, p.proposal_id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "verdict": self.verdict,
            "ok": self.ok,
            "counts": dict(self.counts),
            "proposals": [p.to_dict() for p in self.rank()],
            "signals": list(self.signals),
            "notes": list(self.notes),
            "requires_review": True,
            "bypass_available": self.bypass_available,
            "ts_ms": self.ts_ms,
        }


@dataclass
class LearningRecord:
    """A durable, human-readable memory of what a cycle concluded."""

    cycle_id: str
    summary: str
    proposal_ids: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    verdict: str = "all_clear"
    record_id: str = field(default_factory=lambda: new_id("learn"))
    ts_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "cycle_id": self.cycle_id,
            "summary": self.summary,
            "proposal_ids": list(self.proposal_ids),
            "counts": dict(self.counts),
            "verdict": self.verdict,
            "ts_ms": self.ts_ms,
        }


# Backwards-friendly alias: an "Improvement" is a LearningRecord.
Improvement = LearningRecord


class ProposalStore:
    """Append-only backlog on disk (JSON lines). Best-effort, never fatal."""

    def __init__(self, directory: str = "./data/evolution") -> None:
        self.directory = directory
        self.path = os.path.join(directory, "backlog.jsonl")

    def append(self, report: EvolutionReport) -> str:
        os.makedirs(self.directory, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        return self.path

    def load(self) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        records: list[dict[str, Any]] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    # A corrupt line is skipped, never silently trusted.
                    continue
        return records


class EvolutionAgent(Agent):
    """Observe the system, propose bounded improvements, act on nothing."""

    name = "evolution"
    description = "Observes the system's own behaviour and proposes improvements."

    def __init__(
        self,
        *,
        config: EvolutionConfig | None = None,
        collector: SignalCollector | None = None,
        generator: Any = None,
        store: ProposalStore | None = None,
        memory: Any = None,
        tool_request: Any = None,
    ) -> None:
        super().__init__(tool_request)
        self.config = config or EvolutionConfig()
        self.collector = collector
        self.generator = generator
        self.store = store
        self.memory = memory
        self._last_report: EvolutionReport | None = None

    # ------------------------------------------------------------------
    def run(self, task: AgentTask) -> AgentResult:
        self.state = AgentState.RUNNING
        try:
            report = self.observe(task)
        except Exception as exc:  # noqa: BLE001 - a failed cycle is recorded, not hidden
            self.state = AgentState.FAILED
            return AgentResult(
                agent=self.name,
                task_id=task.id,
                status=AgentState.FAILED,
                error=str(exc),
            )
        self.state = AgentState.SUCCESS
        self._last_report = report
        return AgentResult(
            agent=self.name,
            task_id=task.id,
            status=AgentState.SUCCESS,
            output=report.to_dict(),
            confidence=1.0 if report.ok else 0.6,
            metadata={
                "cycle_id": report.cycle_id,
                "verdict": report.verdict,
                "proposals": len(report.proposals),
                "counts": dict(report.counts),
            },
        )

    # ------------------------------------------------------------------
    def observe(self, task: AgentTask | None = None) -> EvolutionReport:
        """Collect signals, build proposals, and return a bounded report."""
        signals = self._collect_signals(task)
        proposals = self._propose(signals)
        proposals, notes = self._apply_bounds(proposals)
        counts = summarize(signals)
        verdict = self._verdict(signals)
        report = EvolutionReport(
            cycle_id=new_id("cycle"),
            signals=[s.to_dict() for s in signals],
            proposals=proposals,
            counts=counts,
            verdict=verdict,
            notes=notes,
        )
        self._record(report)
        return report

    @property
    def last_report(self) -> EvolutionReport | None:
        return self._last_report

    # ------------------------------------------------------------------
    def _collect_signals(self, task: AgentTask | None) -> list[Any]:
        # Explicit signals on the task take precedence for that run; otherwise
        # fall back to whatever the collector observes. This lets a caller
        # scope a single cycle without discarding the live collector.
        raw = (task.metadata if task else {}).get("signals")
        if raw:
            return [_coerce_signal(item) for item in raw]
        if self.collector is not None:
            return list(self.collector.collect())
        return []

    def _propose(self, signals: list[Any]) -> list[EvolutionProposal]:
        proposals: list[EvolutionProposal] = []
        for signal in signals:
            if isinstance(signal, WeaknessSignal):
                proposals.append(self._from_weakness(signal))
            elif isinstance(signal, HealthSignal):
                proposals.append(self._from_health(signal))
            elif isinstance(signal, ImprovementSignal):
                proposals.append(self._from_opportunity(signal))
        return proposals

    def _from_weakness(self, signal: WeaknessSignal) -> EvolutionProposal:
        weight = _SEVERITY_WEIGHT.get(signal.severity, 0.5)
        title = f"Fix {signal.component}: {_short(signal.what)}"
        return EvolutionProposal(
            title=title,
            area=signal.component,
            kind="fix",
            rationale=signal.why or "a recorded failure",
            evidence=[e for e in (signal.what, signal.impact) if e],
            priority=_clamp(weight),
            severity=signal.severity,
            source_signal_id=signal.signal_id,
            generated_frame=self._frame(title),
        )

    def _from_health(self, signal: HealthSignal) -> EvolutionProposal:
        weight = _SEVERITY_WEIGHT.get(signal.severity, 0.5)
        title = f"Investigate {signal.metric}={signal.value} (expect {signal.expectation})"
        return EvolutionProposal(
            title=title,
            area="observability",
            kind="investigate",
            rationale="a metric drifted outside its expected band",
            evidence=[f"{signal.metric}={signal.value}", signal.expectation],
            priority=_clamp(weight * 0.9),
            severity=signal.severity,
            source_signal_id=signal.signal_id,
            generated_frame=self._frame(title),
        )

    def _from_opportunity(self, signal: ImprovementSignal) -> EvolutionProposal:
        return EvolutionProposal(
            title=signal.opportunity,
            area=signal.area,
            kind="improve",
            rationale=signal.rationale or "a repeated pattern worth consolidating",
            evidence=[signal.area],
            priority=_clamp(signal.confidence * 0.7),
            severity="low",
            source_signal_id=signal.signal_id,
            generated_frame=self._frame(signal.opportunity),
        )

    def _frame(self, title: str) -> str:
        """Optionally reframe a proposal through the parallel generator.

        The generator only offers a different wording; it never changes what is
        proposed, and its absence changes nothing.
        """
        if self.generator is None:
            return ""
        try:
            result = self.generator.generate(title, shots=32)
            ranked = result.ranked()
            return ranked[0].proposal if ranked else ""
        except Exception:  # noqa: BLE001 - framing is best-effort
            return ""

    def _apply_bounds(
        self, proposals: list[EvolutionProposal]
    ) -> tuple[list[EvolutionProposal], list[str]]:
        notes: list[str] = []
        kept: dict[str, EvolutionProposal] = {}
        for proposal in proposals:
            key = f"{proposal.kind}:{proposal.area}:{proposal.title}"
            existing = kept.get(key)
            if existing is None:
                kept[key] = proposal
            else:
                # Same issue twice: one proposal, higher priority.
                existing.priority = _clamp(max(existing.priority, proposal.priority) + 0.1)
                existing.evidence = sorted({*existing.evidence, *proposal.evidence})

        ranked = sorted(kept.values(), key=lambda p: (-p.priority, p.proposal_id))
        if self.config.min_priority > 0:
            before = len(ranked)
            ranked = [p for p in ranked if p.priority >= self.config.min_priority]
            dropped = before - len(ranked)
            if dropped:
                notes.append(
                    f"{dropped} proposal(s) below min_priority "
                    f"{self.config.min_priority} were dropped"
                )
        if len(ranked) > self.config.max_proposals:
            dropped = len(ranked) - self.config.max_proposals
            ranked = ranked[: self.config.max_proposals]
            notes.append(f"{dropped} lower-priority proposal(s) deferred to a later cycle")
        return ranked, notes

    @staticmethod
    def _verdict(signals: list[Any]) -> str:
        if any(getattr(s, "blocking", False) for s in signals):
            return "attention_required"
        return "all_clear"

    def _record(self, report: EvolutionReport) -> None:
        """Persist a best-effort learning record. Never fatal, never hidden."""
        record = LearningRecord(
            cycle_id=report.cycle_id,
            summary=(
                f"{report.verdict}: {len(report.proposals)} proposal(s), "
                f"{report.counts.get('weakness', 0)} weakness(es)"
            ),
            proposal_ids=[p.proposal_id for p in report.proposals],
            counts=dict(report.counts),
            verdict=report.verdict,
        )
        if self.memory is not None:
            try:
                self.memory.write(
                    _scope_project(),
                    f"evolution:{report.cycle_id}",
                    record.to_dict(),
                    actor=self.config.actor,
                )
            except Exception:  # noqa: BLE001 - memory is best-effort here
                report.notes.append("learning record could not be written to memory")
        if self.store is not None and self.config.persist:
            try:
                self.store.append(report)
            except Exception:  # noqa: BLE001
                report.notes.append("proposal backlog could not be persisted")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _coerce_signal(item: Any) -> Any:
    """Accept a signal object or a plain dict (from task metadata)."""
    if isinstance(item, (WeaknessSignal, HealthSignal, ImprovementSignal)):
        return item
    if isinstance(item, dict):
        kind = item.get("kind", "weakness")
        if kind == "health":
            return HealthSignal(**{k: v for k, v in item.items() if k != "kind"})
        if kind == "improvement":
            return ImprovementSignal(**{k: v for k, v in item.items() if k != "kind"})
        return WeaknessSignal(**{k: v for k, v in item.items() if k != "kind"})
    raise TypeError(f"unsupported signal: {type(item)!r}")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _scope_project() -> Any:
    from genesis.core import MemoryScope

    return MemoryScope.PROJECT
