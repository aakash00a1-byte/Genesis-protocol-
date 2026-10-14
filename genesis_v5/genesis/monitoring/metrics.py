"""Lightweight in-process metrics (counters, gauges, histograms).

No external dependencies; provides the monitoring hooks that a real metrics
backend (Prometheus/OTel) could later sink. Offline-safe and thread-safe.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable


class Metrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, float | int] = {}
        self._histograms: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def incr(self, name: str, by: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + by

    def counter(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def set_gauge(self, name: str, value: float | int) -> None:
        with self._lock:
            self._gauges[name] = value

    def gauge(self, name: str) -> float | int | None:
        with self._lock:
            return self._gauges.get(name)

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms.setdefault(name, []).append(value)

    def histogram(self, name: str) -> dict[str, Any]:
        with self._lock:
            values = self._histograms.get(name, [])
            if not values:
                return {"count": 0}
            return {
                "count": len(values),
                "sum": round(sum(values), 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "mean": round(sum(values) / len(values), 3),
            }

    def snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {"counters": {}, "gauges": {}, "histograms": {}}
        with self._lock:
            result["counters"] = dict(self._counters)
            result["gauges"] = dict(self._gauges)
            result["histograms"] = {
                name: {"count": len(v), "mean": round(sum(v) / len(v), 3) if v else 0}
                for name, v in self._histograms.items()
            }
        return result

    def timed(self, name: str):
        """Decorator factory recording duration histogram + call counter.

        Usage: `@metrics.timed("op")` — returns a decorator that wraps the
        function and records success/error counters plus latency.
        """

        def decorator(fn: Callable[[], Any]) -> Callable[[], Any]:
            def wrapped(*args: Any, **kwargs: Any) -> Any:
                start = time.time()
                try:
                    result = fn(*args, **kwargs)
                    self.incr(f"{name}.success")
                    return result
                except Exception:
                    self.incr(f"{name}.error")
                    raise
                finally:
                    self.observe(name, (time.time() - start) * 1000)

            return wrapped

        return decorator