"""Resource governor and degraded modes (V7 P8).

Under resource pressure (CPU, memory, disk) the system must do *less*, not
thrash. The governor reads a resource snapshot (from ``survival.resource_monitor``
or any callable), classifies it into a mode, and publishes the mode so callers can
degrade gracefully:

* ``normal``   - everything allowed.
* ``reduced``  - expensive/optional work is skipped; core work continues.
* ``minimal``  - only essential work; new autonomous tasks are refused.
* ``halted``   - no new autonomous work at all (still answers, still alerts).

Thresholds are explicit and the *strictest* breach wins, so a single overloaded
dimension cannot be masked by healthy ones. A failed reading does not fabricate a
healthy state: an unreadable snapshot is treated as ``reduced`` (fail toward
caution), never ``normal``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

MODES = ("normal", "reduced", "minimal", "halted")
MODE_RANK = {m: i for i, m in enumerate(MODES)}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Thresholds:
    """Per-dimension percentages at which each mode begins."""

    reduced_cpu: float = 75.0
    minimal_cpu: float = 90.0
    halted_cpu: float = 98.0
    reduced_memory: float = 75.0
    minimal_memory: float = 90.0
    halted_memory: float = 98.0
    reduced_disk: float = 80.0
    minimal_disk: float = 92.0
    halted_disk: float = 98.0

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class ResourceReading:
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    read_ok: bool = True

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class GovernorState:
    mode: str
    reasons: List[str]
    reading: Dict[str, Any]
    at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class ResourceGovernor:
    """Turns a resource reading into a mode and enforces it."""

    def __init__(self, sampler: Optional[Callable[[], ResourceReading]] = None,
                 thresholds: Optional[Thresholds] = None):
        self._sampler = sampler
        self.thresholds = thresholds or Thresholds()
        self._last: Optional[GovernorState] = None

    def sample(self) -> ResourceReading:
        if self._sampler is not None:
            try:
                return self._sampler()
            except Exception:
                return ResourceReading(0.0, 0.0, 0.0, read_ok=False)
        try:
            from genesis_protocol.survival.resource_monitor import get_resource_monitor

            stats = get_resource_monitor().get_all_stats()
            return ResourceReading(
                cpu_percent=float(stats.get("cpu_percent", 0.0)),
                memory_percent=float(stats.get("memory", {}).get("percent", 0.0)),
                disk_percent=float(stats.get("disk", {}).get("percent", 0.0)),
            )
        except Exception:
            return ResourceReading(0.0, 0.0, 0.0, read_ok=False)

    def _mode_for(self, value: float, reduced: float, minimal: float, halted: float,
                  dimension: str, reasons: List[str]) -> str:
        if value >= halted:
            reasons.append(f"{dimension} at {value:.1f}% >= halt {halted:.0f}%")
            return "halted"
        if value >= minimal:
            reasons.append(f"{dimension} at {value:.1f}% >= minimal {minimal:.0f}%")
            return "minimal"
        if value >= reduced:
            reasons.append(f"{dimension} at {value:.1f}% >= reduced {reduced:.0f}%")
            return "reduced"
        return "normal"

    def evaluate(self) -> GovernorState:
        reading = self.sample()
        reasons: List[str] = []
        if not reading.read_ok:
            reasons.append("resource reading failed; erring toward caution")
            mode = "reduced"
        else:
            t = self.thresholds
            candidates = [
                self._mode_for(reading.cpu_percent, t.reduced_cpu, t.minimal_cpu, t.halted_cpu, "cpu", reasons),
                self._mode_for(reading.memory_percent, t.reduced_memory, t.minimal_memory, t.halted_memory,
                               "memory", reasons),
                self._mode_for(reading.disk_percent, t.reduced_disk, t.minimal_disk, t.halted_disk, "disk", reasons),
            ]
            mode = max(candidates, key=lambda m: MODE_RANK[m])
        if not reasons:
            reasons.append("all dimensions within limits")
        state = GovernorState(mode=mode, reasons=reasons, reading=reading.to_dict())
        self._last = state
        return state

    @staticmethod
    def permits(mode: str, work: str) -> bool:
        """Whether ``work`` may run in ``mode``.

        ``essential`` runs in every mode; ``standard`` needs ``normal`` or
        ``reduced``; ``optional`` needs ``normal``.
        """
        if work == "essential":
            return True
        if work == "standard":
            return MODE_RANK.get(mode, 0) <= MODE_RANK["reduced"]
        if work == "optional":
            return mode == "normal"
        return False

    def mode(self) -> str:
        if self._last is None:
            return self.evaluate().mode
        return self._last.mode

    def status(self) -> Dict[str, object]:
        return {"mode": self.mode(), "last": self._last.to_dict() if self._last else None,
                "thresholds": self.thresholds.to_dict()}
