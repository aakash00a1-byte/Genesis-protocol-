"""Health checks registry for /health and /ready endpoints."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthCheck:
    name: str
    status: HealthStatus = HealthStatus.OK
    detail: str = ""
    checked_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "detail": self.detail,
            "checked_ms": self.checked_ms,
        }


Checker = Callable[[], tuple[HealthStatus, str]]


class HealthRegistry:
    """Registers named checks; aggregates into liveness/readiness views."""

    def __init__(self) -> None:
        self._checks: dict[str, Checker] = {}
        self._lock = threading.Lock()

    def register(self, name: str, checker: Checker) -> None:
        with self._lock:
            self._checks[name] = checker

    def run_all(self) -> list[HealthCheck]:
        results: list[HealthCheck] = []
        with self._lock:
            names = list(self._checks)
        import time

        for name in names:
            try:
                status, detail = self._checks[name]()
            except Exception as exc:  # noqa: BLE001 — a check must never crash
                status, detail = HealthStatus.UNHEALTHY, f"check raised: {exc}"
            results.append(
                HealthCheck(
                    name=name,
                    status=status,
                    detail=detail,
                    checked_ms=int(time.time() * 1000),
                )
            )
        return results

    def status(self) -> HealthStatus:
        states = {c.status for c in self.run_all()}
        if states == {HealthStatus.OK}:
            return HealthStatus.OK
        if any(s == HealthStatus.UNHEALTHY for s in states):
            return HealthStatus.UNHEALTHY
        return HealthStatus.DEGRADED

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status().value,
            "checks": [c.to_dict() for c in self.run_all()],
        }