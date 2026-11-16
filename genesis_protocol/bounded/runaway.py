"""Runaway-loop detection (V7 P8).

The most common way an autonomous system misbehaves is by looping: retrying the
same action, cycling through the same few states, or making no progress while
spending budget. ``RunawayGuard`` watches a stream of ``(action, signature)``
steps and flags three distinct patterns:

* **Repetition** - the same action signature repeated more than ``max_repeats``
  times in a row.
* **Cycling** - the last ``cycle_len`` distinct signatures repeat as a block.
* **No progress** - many steps with the same progress marker.

Each detector is a pure function of the recorded window, so its decision is
reproducible and testable. The guard only *detects*; the caller decides to stop.
"""
from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RunawayFinding:
    kind: str
    reason: str
    repeats: int = 0
    window: List[str] = field(default_factory=list)
    at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


class RunawayGuard:
    """Detects repetition, cycling and no-progress loops in a step stream."""

    def __init__(self, max_repeats: int = 3, cycle_len: int = 3,
                 max_same_progress: int = 5, window: int = 50):
        self.max_repeats = max(1, int(max_repeats))
        self.cycle_len = max(2, int(cycle_len))
        self.max_same_progress = max(1, int(max_same_progress))
        self.window = max(4, int(window))
        self._steps: Deque[str] = deque(maxlen=self.window)
        self._progress: Deque[str] = deque(maxlen=self.window)

    def reset(self) -> None:
        self._steps.clear()
        self._progress.clear()

    # -- observation ----------------------------------------------------------

    def record(self, action: str, signature: str = "", progress: str = "") -> Optional[RunawayFinding]:
        """Record one step and return a finding if it makes the stream runaway."""
        token = f"{action}:{signature}" if signature else str(action)
        self._steps.append(token)
        if progress:
            self._progress.append(str(progress))
        return self.detect()

    def detect(self) -> Optional[RunawayFinding]:
        repeat = self._detect_repetition()
        if repeat:
            return repeat
        cycle = self._detect_cycle()
        if cycle:
            return cycle
        return self._detect_no_progress()

    # -- detectors ------------------------------------------------------------

    def _detect_repetition(self) -> Optional[RunawayFinding]:
        steps = list(self._steps)
        if len(steps) < self.max_repeats:
            return None
        tail = steps[-self.max_repeats:]
        if len(set(tail)) == 1:
            return RunawayFinding(
                kind="repetition", repeats=len(tail),
                reason=f"'{tail[0]}' repeated {len(tail)} times in a row",
                window=steps[-self.max_repeats * 2:],
            )
        return None

    def _detect_cycle(self) -> Optional[RunawayFinding]:
        steps = list(self._steps)
        n = self.cycle_len
        if len(steps) < n * 2:
            return None
        block = steps[-n:]
        previous = steps[-2 * n:-n]
        # A cycle is the same ordered block repeated, with at least two distinct
        # members (a single repeated value is "repetition", handled above).
        if block == previous and len(set(block)) >= 2:
            return RunawayFinding(
                kind="cycle", repeats=2,
                reason=f"a {n}-step cycle repeated: {block}",
                window=steps[-2 * n:],
            )
        return None

    def _detect_no_progress(self) -> Optional[RunawayFinding]:
        progress = list(self._progress)
        if len(progress) < self.max_same_progress:
            return None
        tail = progress[-self.max_same_progress:]
        if len(set(tail)) == 1:
            return RunawayFinding(
                kind="no_progress", repeats=len(tail),
                reason=f"no progress across {len(tail)} steps (marker '{tail[0]}')",
                window=list(self._steps)[-self.max_same_progress:],
            )
        return None

    def status(self) -> Dict[str, object]:
        return {"max_repeats": self.max_repeats, "cycle_len": self.cycle_len,
                "max_same_progress": self.max_same_progress, "steps": len(self._steps)}
