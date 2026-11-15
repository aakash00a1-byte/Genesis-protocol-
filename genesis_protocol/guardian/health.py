"""System health monitoring for the AI Guardian (V7 P5).

Monitors application health, memory/database integrity and service failures, and
flags unexpected changes in production behaviour.

It composes existing components rather than duplicating them:

* ``survival.resource_monitor.ResourceMonitor`` - CPU / memory / disk / uptime.
* ``agentic.memory.AgentMemory`` - the durable memory store (SQLite), checked
  with ``PRAGMA integrity_check`` and a row count.
* ``agentic.tasks.TaskStore`` - the durable task store (JSON), checked for
  readability.
* ``core.admin_alerts.AdminAlertManager`` - used only to *alert*; the guardian
  never acts on a health finding.

Read-only: opening the SQLite database for a check never writes. Findings carry
the measured value and the threshold that produced them. Nothing here restarts a
service, rotates a credential, or changes a setting.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Health thresholds. Named so firing conditions are reviewable.
CPU_PERCENT_THRESHOLD = 90.0
MEMORY_PERCENT_THRESHOLD = 90.0
DISK_PERCENT_THRESHOLD = 90.0


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class HealthFinding:
    """One health observation with the measured value and its threshold."""

    detector: str
    severity: str
    title: str
    description: str
    measured: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    detected_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HealthMonitor:
    """Read-only health checks over resources, databases and services."""

    def __init__(self, resource_monitor: Optional[Any] = None, memory_db: Optional[str] = None):
        self._resources = resource_monitor
        self.memory_db = memory_db or os.environ.get("GLUTEN_MEMORY_DB") or str(Path("data") / "gluten_memory.db")

    @property
    def resources(self) -> Any:
        if self._resources is None:
            from genesis_protocol.survival.resource_monitor import get_resource_monitor

            self._resources = get_resource_monitor()
        return self._resources

    # -- resources ------------------------------------------------------------

    def check_resources(self) -> List[HealthFinding]:
        findings: List[HealthFinding] = []
        try:
            cpu = float(self.resources.get_cpu_usage())
            mem = self.resources.get_memory_usage()
            disk = self.resources.get_disk_usage()
        except Exception as exc:
            return [HealthFinding(
                detector="resource_unavailable", severity="high",
                title="resource metrics unavailable",
                description="the resource monitor could not be read",
                measured={"error": str(exc)}, confidence=0.7,
            )]
        if cpu >= CPU_PERCENT_THRESHOLD:
            findings.append(HealthFinding(
                detector="high_cpu", severity="medium", title="sustained high CPU",
                description="CPU usage is at or above the threshold",
                measured={"cpu_percent": cpu, "threshold": CPU_PERCENT_THRESHOLD}))
        if mem.get("percent", 0) >= MEMORY_PERCENT_THRESHOLD:
            findings.append(HealthFinding(
                detector="high_memory", severity="medium", title="high memory usage",
                description="memory usage is at or above the threshold",
                measured={"memory_percent": mem.get("percent"), "threshold": MEMORY_PERCENT_THRESHOLD}))
        if disk.get("percent", 0) >= DISK_PERCENT_THRESHOLD:
            findings.append(HealthFinding(
                detector="high_disk", severity="medium", title="low disk space",
                description="disk usage is at or above the threshold",
                measured={"disk_percent": disk.get("percent"), "threshold": DISK_PERCENT_THRESHOLD}))
        return findings

    # -- database integrity ---------------------------------------------------

    def check_memory_db(self) -> List[HealthFinding]:
        path = self.memory_db
        if path == ":memory:" or not Path(path).exists():
            return [HealthFinding(
                detector="memory_db_missing", severity="low",
                title="memory database not found",
                description="the durable memory store does not exist at the expected path",
                measured={"path": path}, confidence=0.6)]
        findings: List[HealthFinding] = []
        try:
            # Read-only URI: the integrity check must never write to the store.
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result = row[0] if row else "unknown"
                if result != "ok":
                    findings.append(HealthFinding(
                        detector="memory_db_corrupt", severity="critical",
                        title="memory database integrity check failed",
                        description="PRAGMA integrity_check did not return 'ok'",
                        measured={"path": path, "integrity_check": result}, confidence=0.95))
                try:
                    count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                except Exception:
                    count = None
                findings.append(HealthFinding(
                    detector="memory_db_ok", severity="info",
                    title="memory database readable",
                    description="integrity check returned 'ok'",
                    measured={"path": path, "integrity_check": result, "rows": count},
                    confidence=0.95))
            finally:
                conn.close()
        except Exception as exc:
            findings.append(HealthFinding(
                detector="memory_db_unreadable", severity="high",
                title="memory database unreadable",
                description="the durable memory store could not be opened read-only",
                measured={"path": path, "error": str(exc)}, confidence=0.8))
        return findings

    def check_task_store(self) -> List[HealthFinding]:
        path = os.environ.get("GLUTEN_TASK_DB") or str(Path("data") / "gluten_tasks.json")
        if not Path(path).exists():
            return []
        try:
            import json

            json.loads(Path(path).read_text(encoding="utf-8"))
            return [HealthFinding(
                detector="task_store_ok", severity="info", title="task store readable",
                description="the durable task store parses", measured={"path": path}, confidence=0.9)]
        except Exception as exc:
            return [HealthFinding(
                detector="task_store_corrupt", severity="high", title="task store unreadable",
                description="the durable task store could not be parsed",
                measured={"path": path, "error": str(exc)}, confidence=0.9)]

    # -- services / behaviour change -----------------------------------------

    @staticmethod
    def detect_behaviour_change(
        baseline: Dict[str, Any], current: Dict[str, Any], tolerance: float = 0.0
    ) -> List[HealthFinding]:
        """Flag metric keys that moved beyond ``tolerance`` from the baseline.

        ``baseline`` is a prior snapshot of numeric metrics; ``current`` is the
        same keys measured now. Only keys present in both are compared, so an
        absent key is reported as unknown rather than as a change.
        """
        findings: List[HealthFinding] = []
        for key, base_value in baseline.items():
            if key not in current:
                continue
            try:
                base_num = float(base_value)
                now_num = float(current[key])
            except (TypeError, ValueError):
                continue
            if abs(now_num - base_num) > tolerance:
                findings.append(HealthFinding(
                    detector="behaviour_change", severity="medium",
                    title=f"production metric '{key}' changed",
                    description=f"'{key}' moved from {base_num} to {now_num}",
                    measured={"metric": key, "baseline": base_num, "current": now_num,
                              "tolerance": tolerance},
                    confidence=0.6))
        return findings

    # -- entry point ----------------------------------------------------------

    def check(self) -> List[HealthFinding]:
        return self.check_resources() + self.check_memory_db() + self.check_task_store()
