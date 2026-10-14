"""Runtime lifecycle: health/readiness endpoints, graceful shutdown, and
worker lifecycle management.

Offline-safe and dependency-free. Provides the production hooks (health,
readiness, shutdown, worker pool) that a real web/server layer can mount.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class HealthReport:
    status: str  # "ok" | "degraded" | "unhealthy"
    checks: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checks": self.checks,
        }


class RuntimeHealth:
    """Liveness + readiness checks.

    - `health()` is liveness: the process is up and core deps are reachable.
    - `ready()` additionally requires that startup completed and workers are
      available.
    """

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], tuple[bool, str]]] = {}
        self._started_ms: int = 0
        self._ready = False
        self._lock = threading.Lock()

    def start(self) -> None:
        from genesis.core import now_ms

        with self._lock:
            self._started_ms = now_ms()

    def register(self, name: str, check: Callable[[], tuple[bool, str]]) -> None:
        with self._lock:
            self._checks[name] = check

    def set_ready(self, ready: bool = True) -> None:
        with self._lock:
            self._ready = ready

    def _run(self) -> list[dict[str, Any]]:
        with self._lock:
            names = list(self._checks)
        results: list[dict[str, Any]] = []
        for name in names:
            try:
                ok, detail = self._checks[name]()
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, f"check raised: {exc}"
            results.append({"name": name, "ok": ok, "detail": detail})
        return results

    def health(self) -> HealthReport:
        checks = self._run()
        status = "ok" if all(c["ok"] for c in checks) else "unhealthy"
        return HealthReport(status=status, checks=checks)

    def ready(self) -> HealthReport:
        checks = self._run()
        ok = all(c["ok"] for c in checks)
        with self._lock:
            ready = self._ready
        if not ready:
            return HealthReport(
                status="degraded",
                checks=checks + [{"name": "startup", "ok": False, "detail": "not ready"}],
            )
        status = "ok" if ok else "unhealthy"
        return HealthReport(status=status, checks=checks)


class WorkerPool:
    """Bounded worker lifecycle: start, submit, drain, stop.

    Implements a bounded queue + worker threads. Used for graceful shutdown
    (drain in-flight work) and resource limits (max_workers).
    """

    def __init__(self, max_workers: int = 4, queue_size: int = 100) -> None:
        self.max_workers = max(1, max_workers)
        self._queue: queue.Queue[Callable[[], Any]] = queue.Queue(maxsize=queue_size)
        self._workers: list[threading.Thread] = []
        self._stop = threading.Event()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._stop.clear()
        for i in range(self.max_workers):
            thread = threading.Thread(
                target=self._run_worker, name=f"genesis-worker-{i}", daemon=True
            )
            thread.start()
            self._workers.append(thread)
        self._started = True

    def submit(self, fn: Callable[[], Any]) -> bool:
        """Enqueue work. Returns False if the pool is stopping or full."""
        if self._stop.is_set():
            return False
        try:
            self._queue.put_nowait(fn)
            return True
        except queue.Full:
            return False

    def _run_worker(self) -> None:
        while True:
            try:
                fn = self._queue.get(timeout=0.2)
            except queue.Empty:
                # Exit only when stopped AND the queue is drained.
                if self._stop.is_set():
                    return
                continue
            try:
                fn()
            except Exception:  # noqa: BLE001 — worker must survive task errors
                pass
            finally:
                self._queue.task_done()

    def drain(self, timeout_seconds: float = 10.0) -> None:
        """Wait for queued + in-flight work to finish (bounded)."""
        self._queue.join()
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if all(not w.is_alive() for w in self._workers):
                return
            time.sleep(0.05)

    def stop(self, timeout_seconds: float = 10.0) -> None:
        """Graceful shutdown: stop accepting work, drain, join workers."""
        self._stop.set()
        self.drain(timeout_seconds)
        for worker in self._workers:
            worker.join(timeout=timeout_seconds)
        self._workers.clear()
        self._started = False

    @property
    def active(self) -> int:
        return sum(1 for w in self._workers if w.is_alive())

    @property
    def queued(self) -> int:
        return self._queue.qsize()


class ApplicationRuntime:
    """Ties health, readiness, workers, and graceful shutdown together."""

    def __init__(
        self,
        *,
        max_workers: int = 4,
        shutdown_timeout_seconds: float = 10.0,
    ) -> None:
        self.health = RuntimeHealth()
        self.workers = WorkerPool(max_workers=max_workers)
        self.shutdown_timeout = shutdown_timeout_seconds
        self._shutdown_hooks: list[Callable[[], None]] = []
        self._started = False

    def start(self) -> None:
        self.health.start()
        self.workers.start()
        self._started = True
        self.health.set_ready(True)

    def on_shutdown(self, hook: Callable[[], None]) -> None:
        self._shutdown_hooks.append(hook)

    def shutdown(self) -> None:
        """Graceful shutdown: run hooks, drain workers, mark not ready."""
        self.health.set_ready(False)
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        self.workers.stop(timeout_seconds=self.shutdown_timeout)
        self._started = False

    def status(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "health": self.health.health().to_dict(),
            "ready": self.health.ready().to_dict(),
            "workers": {
                "max": self.workers.max_workers,
                "active": self.workers.active,
                "queued": self.workers.queued,
            },
        }