"""Self-diagnostics (V7 cross-phase).

A *capability*, not a phase: it reports the health of the systems built across
V7 (identity, policy, memory, guardian, recovery, evolution, mission, …) so a
degraded subsystem is visible instead of silently failing.

Design rules:

* **Never a substitute for the phase it checks.** A diagnostic *observes*; it
  does not run missions, land changes or take defensive action.
* **Fail soft.** A subsystem that is absent (its phase not deployed) is reported
  ``missing``, not an error - so this package is mergeable on its own.
* **Fail closed on real breakage.** A check that raises is reported ``error``.
* **Read-only.** Checks must not mutate state; the report is the output.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_MISSING = "missing"
STATUS_ERROR = "error"

_SEVERITY = {STATUS_OK: "info", STATUS_DEGRADED: "medium",
             STATUS_MISSING: "info", STATUS_ERROR: "high"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CheckResult:
    name: str
    phase: str
    status: str
    detail: str = ""
    duration_ms: int = 0

    @property
    def severity(self) -> str:
        return _SEVERITY.get(self.status, "info")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity
        return data


@dataclass
class DiagnosticReport:
    checked_at: str = field(default_factory=utcnow)
    results: List[CheckResult] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return all(r.status in (STATUS_OK, STATUS_MISSING) for r in self.results)

    def to_dict(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return {
            "checked_at": self.checked_at,
            "healthy": self.healthy,
            "counts": counts,
            "results": [r.to_dict() for r in self.results],
        }


class DiagnosticCheck:
    """One named probe of a subsystem.

    ``probe`` returns ``(ok, detail)``; ``(None, detail)`` means the subsystem is
    absent (reported ``missing`` rather than an error).
    """

    def __init__(self, name: str, phase: str, probe: Callable[[], Any]):
        self.name = name
        self.phase = phase
        self.probe = probe

    def run(self) -> CheckResult:
        import time

        start = time.time()
        try:
            outcome = self.probe()
        except Exception as exc:  # a broken probe is an error finding, not a crash
            return CheckResult(self.name, self.phase, STATUS_ERROR,
                               f"{type(exc).__name__}: {exc}",
                               int((time.time() - start) * 1000))
        duration = int((time.time() - start) * 1000)

        if isinstance(outcome, tuple):
            ok, detail = outcome
        else:
            ok, detail = bool(outcome), ""

        if ok is None:
            status = STATUS_MISSING
        elif ok:
            status = STATUS_OK
        else:
            status = STATUS_DEGRADED
        return CheckResult(self.name, self.phase, status, str(detail), duration)


def _try_import(module: str) -> Any:
    import importlib

    try:
        return importlib.import_module(module)
    except Exception:
        return None


def default_checks() -> List[DiagnosticCheck]:
    """The standard cross-phase battery. Each probe is read-only and defensive."""

    def policy_probe():
        mod = _try_import("genesis_protocol.agentic.policy")
        if mod is None:
            return (None, "policy module absent")
        # A healthy policy refuses a genuinely privileged operation.
        decision = mod.get_agent_policy().authorize_operation(0, "merge_pr")
        return (not decision.allowed, "privileged operation refused")

    def identity_probe():
        mod = _try_import("genesis_protocol.agentic.identity_registry")
        if mod is None:
            return (None, "identity module absent")
        registry = mod.get_identity_registry()
        result = registry.verify("does-not-exist")
        return (not result.ok, "unknown identity refused")

    def memory_probe():
        mod = _try_import("genesis_protocol.agentic.memory")
        if mod is None:
            return (None, "memory module absent")
        return (True, "memory module importable")

    def audit_probe():
        mod = _try_import("genesis_protocol.agentic.audit")
        if mod is None:
            return (None, "audit module absent")
        log = mod.get_audit_log()
        return (hasattr(log, "record") and hasattr(log, "tail"), "audit sink available")

    def recovery_probe():
        mod = _try_import("genesis_protocol.recovery")
        if mod is None or getattr(mod, "BackupVault", None) is None:
            return (None, "recovery package absent (P8B not deployed)")
        return (True, "recovery package importable")

    def evolution_probe():
        mod = _try_import("genesis_protocol.evolution")
        engine_cls = getattr(mod, "EvolutionEngine", None) if mod is not None else None
        if engine_cls is None:
            return (None, "evolution package absent (P9 not deployed)")
        exposed = {n for n in dir(engine_cls()) if not n.startswith("_")}
        forbidden = {"merge", "deploy", "push", "publish", "land", "approve"}
        return (forbidden.isdisjoint(exposed), "engine has no land/deploy path")

    def mission_probe():
        mod = _try_import("genesis_protocol.mission")
        manager_cls = getattr(mod, "MissionManager", None) if mod is not None else None
        if manager_cls is None:
            return (None, "mission package absent (P10 not deployed)")
        exposed = {n for n in dir(manager_cls()) if not n.startswith("_")}
        forbidden = {"merge", "deploy", "push", "publish", "set_secret"}
        return (forbidden.isdisjoint(exposed), "manager has no privileged path")

    def resource_probe():
        mod = _try_import("genesis_protocol.survival.resource_monitor")
        if mod is None:
            return (None, "resource monitor absent")
        stats = mod.get_resource_monitor().get_all_stats()
        return (isinstance(stats, dict) and bool(stats), "resource stats readable")

    def observability_probe():
        mod = _try_import("genesis_protocol.observability")
        if mod is None:
            return (None, "observability module absent")
        return (hasattr(mod, "get_observability"), "observability available")

    return [
        DiagnosticCheck("policy_fails_closed", "P1/P2", policy_probe),
        DiagnosticCheck("identity_fails_closed", "P2", identity_probe),
        DiagnosticCheck("memory_available", "P3", memory_probe),
        DiagnosticCheck("audit_available", "P2", audit_probe),
        DiagnosticCheck("recovery_available", "P8B", recovery_probe),
        DiagnosticCheck("evolution_propose_only", "P9", evolution_probe),
        DiagnosticCheck("mission_no_privileged_path", "P10", mission_probe),
        DiagnosticCheck("resources_readable", "P8B", resource_probe),
        DiagnosticCheck("observability_available", "P4", observability_probe),
    ]
