"""A small HTTP service over the generation and authority pipeline.

Zero dependencies: it uses only ``http.server`` from the standard library, so
it runs in the same offline environment as everything else. The service exposes
generation and governed submission — there is no endpoint that executes raw
input without passing through the authority gate.

Endpoints:

- ``GET  /healthz``   liveness
- ``GET  /readyz``    readiness
- ``GET  /v1/status`` metrics and transparency summary
- ``POST /v1/generate``        raw input -> ranked proposals (no side effects)
- ``POST /v1/submit``          raw input + tool requests -> governed outcomes

``POST /v1/submit`` is the only path that can cause an action, and it goes
through ``AuthorityPipeline``: policy, permissions, sandbox, audit. The gate is
not optional and cannot be turned off by a request field.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from genesis.generation.generator import ParallelGenerator
from genesis.monitoring.metrics import Metrics
from genesis.pipeline.authority import AuthorityPipeline
from genesis.tools.gateway import ToolRequest


class GenesisService:
    """The application object behind the HTTP layer."""

    def __init__(
        self,
        generator: ParallelGenerator,
        pipeline: AuthorityPipeline,
        *,
        metrics: Metrics | None = None,
        status_provider: Any = None,
    ) -> None:
        self.generator = generator
        self.pipeline = pipeline
        self.metrics = metrics or Metrics()
        self.status_provider = status_provider

    # ------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return {"status": "ok"}

    def ready(self) -> dict[str, Any]:
        return {"status": "ready"}

    def status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"metrics": self.metrics.snapshot()}
        if self.status_provider is not None:
            payload["runtime"] = self.status_provider()
        return payload

    def generate(self, raw_input: str, *, shots: int = 256) -> dict[str, Any]:
        result = self.pipeline.propose(raw_input, shots=shots)
        self.metrics.incr("generate.requests")
        self.metrics.observe("generate.branches", float(len(result.generation.branches)))
        return result.to_dict()

    def submit(self, raw_input: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
        tool_requests = [self._to_request(r) for r in requests]
        result = self.pipeline.submit(raw_input, tool_requests)
        self.metrics.incr("submit.requests")
        self.metrics.incr("submit.executed", result.executed)
        self.metrics.incr("submit.denied", result.denied)
        return result.to_dict()

    @staticmethod
    def _to_request(payload: dict[str, Any]) -> ToolRequest:
        return ToolRequest(
            tool=str(payload.get("tool", "")),
            args=dict(payload.get("args", {})),
            actor=str(payload.get("actor", "unknown")),
            role=str(payload.get("role", "none")),
            cwd=str(payload.get("cwd", "/workspace")),
        )


def _make_handler(service: GenesisService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Genesis/1.0"

        def log_message(self, *args: Any) -> None:  # keep the console quiet
            return

        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send(200, service.health())
            elif self.path == "/readyz":
                self._send(200, service.ready())
            elif self.path == "/v1/status":
                self._send(200, service.status())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            payload = self._read_json()
            raw_input = str(payload.get("input", ""))
            if self.path == "/v1/generate":
                shots = int(payload.get("shots", 256))
                self._send(200, service.generate(raw_input, shots=shots))
            elif self.path == "/v1/submit":
                requests = payload.get("requests", [])
                if not isinstance(requests, list):
                    self._send(400, {"error": "requests must be a list"})
                    return
                self._send(200, service.submit(raw_input, requests))
            else:
                self._send(404, {"error": "not found"})

    return Handler


def serve(
    service: GenesisService,
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    background: bool = False,
) -> ThreadingHTTPServer:
    """Start the HTTP service. Set ``background=True`` to return immediately."""
    httpd = ThreadingHTTPServer((host, port), _make_handler(service))
    if background:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
    else:
        httpd.serve_forever()
    return httpd
