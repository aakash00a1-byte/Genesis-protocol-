"""Resource awareness (V7 P10).

A mission must know what it costs before it runs. This module reuses the
canonical survival layer (``survival.resource_monitor``, ``survival.cost_tracker``)
rather than reading the host itself, and answers one question: *may this step
run within the budget I was given?*

It fails closed. An unreadable reading is treated as a breach (the step is
refused), and an unknown cost is assumed to be the worst case, never zero.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ResourceBudget:
    """Limits a mission must respect. ``None`` means 'not constrained'."""

    max_cost: Optional[float] = None
    max_tokens: Optional[int] = None
    max_steps: Optional[int] = None
    max_cpu_percent: Optional[float] = None
    max_memory_percent: Optional[float] = None


@dataclass
class ResourceSnapshot:
    cpu_percent: Optional[float] = None
    memory_percent: Optional[float] = None
    disk_percent: Optional[float] = None
    cost_today: Optional[float] = None
    tokens_used: int = 0
    steps_used: int = 0
    readable: bool = True
    at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceDecision:
    ok: bool
    reason: str
    snapshot: ResourceSnapshot

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "snapshot": self.snapshot.to_dict()}


class ResourceGovernor:
    """Answers whether a step fits the mission's budget."""

    def __init__(self, monitor: Optional[Any] = None, cost_tracker: Optional[Any] = None):
        self._monitor = monitor
        self._cost = cost_tracker

    @property
    def monitor(self) -> Any:
        if self._monitor is None:
            try:
                from genesis_protocol.survival.resource_monitor import get_resource_monitor

                self._monitor = get_resource_monitor()
            except Exception:
                self._monitor = None
        return self._monitor

    @property
    def cost_tracker(self) -> Any:
        if self._cost is None:
            try:
                from genesis_protocol.survival.cost_tracker import get_cost_tracker

                self._cost = get_cost_tracker()
            except Exception:
                self._cost = None
        return self._cost

    def snapshot(self, tokens_used: int = 0, steps_used: int = 0) -> ResourceSnapshot:
        snap = ResourceSnapshot(tokens_used=tokens_used, steps_used=steps_used)
        monitor = self.monitor
        if monitor is None:
            snap.readable = False
            return snap
        try:
            stats = monitor.get_all_stats() or {}
            cpu = stats.get("cpu") or {}
            mem = stats.get("memory") or {}
            disk = stats.get("disk") or {}
            snap.cpu_percent = _number(cpu.get("percent") if isinstance(cpu, dict) else cpu)
            snap.memory_percent = _number(mem.get("percent") if isinstance(mem, dict) else mem)
            snap.disk_percent = _number(disk.get("percent") if isinstance(disk, dict) else disk)
        except Exception:
            snap.readable = False
        tracker = self.cost_tracker
        if tracker is not None:
            try:
                snap.cost_today = float(tracker.get_today())
            except Exception:
                snap.cost_today = None
        return snap

    def check(self, budget: ResourceBudget, *, estimated_cost: float = 0.0,
              estimated_tokens: int = 0, tokens_used: int = 0,
              steps_used: int = 0) -> ResourceDecision:
        """Decide whether one more step fits. Fails closed on any uncertainty."""
        snap = self.snapshot(tokens_used=tokens_used, steps_used=steps_used)

        if budget.max_steps is not None and steps_used + 1 > budget.max_steps:
            return ResourceDecision(False, f"step budget exhausted ({steps_used}/{budget.max_steps})", snap)

        if budget.max_tokens is not None and tokens_used + estimated_tokens > budget.max_tokens:
            return ResourceDecision(
                False,
                f"token budget exhausted ({tokens_used + estimated_tokens}/{budget.max_tokens})",
                snap,
            )

        if budget.max_cost is not None and snap.cost_today is not None:
            if snap.cost_today + estimated_cost > budget.max_cost:
                return ResourceDecision(
                    False,
                    f"cost budget exhausted ({snap.cost_today + estimated_cost:.4f}/{budget.max_cost})",
                    snap,
                )

        for limit, observed, label in (
            (budget.max_cpu_percent, snap.cpu_percent, "cpu"),
            (budget.max_memory_percent, snap.memory_percent, "memory"),
        ):
            if limit is None:
                continue
            if observed is None:
                # Unreadable reading -> refuse (fail closed), never assume headroom.
                return ResourceDecision(False, f"{label} usage unreadable; refusing to proceed", snap)
            if observed > limit:
                return ResourceDecision(False, f"{label} usage {observed:.1f}% exceeds {limit:.1f}%", snap)

        return ResourceDecision(True, "within budget", snap)


def _number(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
