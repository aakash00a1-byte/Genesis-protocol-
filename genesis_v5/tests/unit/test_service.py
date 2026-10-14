"""Tests for the HTTP service: generation and governed submission over HTTP."""
from __future__ import annotations

import json
import threading
import urllib.request

import pytest

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.pipeline.authority import AuthorityPipeline
from genesis.service.http import GenesisService, serve


@pytest.fixture()
def base_url() -> str:
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    generator = ParallelGenerator(seed=1)
    pipeline = AuthorityPipeline(generator, kernel.gateway)
    service = GenesisService(generator, pipeline)
    httpd = serve(service, host="127.0.0.1", port=0, background=True)
    host, port = httpd.server_address[0], httpd.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def test_health_and_ready(base_url: str) -> None:
    assert _get(f"{base_url}/healthz")[1]["status"] == "ok"
    assert _get(f"{base_url}/readyz")[1]["status"] == "ready"


def test_generate_returns_proposals_without_side_effects(base_url: str) -> None:
    status, body = _post(f"{base_url}/v1/generate", {"input": "raw !! input", "shots": 64})
    assert status == 200
    assert body["raw_input"] == "raw !! input"
    assert body["executed"] == 0
    assert body["bypass_available"] is False
    assert len(body["generation"]["branches"]) == 3


def test_submit_denies_a_write_and_records_the_reason(base_url: str) -> None:
    payload = {
        "input": "write a file",
        "requests": [
            {
                "tool": "file.write",
                "args": {"path": "/workspace/http_should_not_exist.txt", "content": "x"},
                "actor": "demo",
                "role": "researcher",
                "cwd": "/workspace",
            }
        ],
    }
    status, body = _post(f"{base_url}/v1/submit", payload)
    assert status == 200
    assert body["denied"] == 1
    assert body["actions"][0]["reason"]
    from pathlib import Path

    assert not Path("/workspace/http_should_not_exist.txt").exists()


def test_status_exposes_metrics(base_url: str) -> None:
    _post(f"{base_url}/v1/generate", {"input": "x", "shots": 32})
    status, body = _get(f"{base_url}/v1/status")
    assert status == 200
    assert "metrics" in body


def test_unknown_path_is_404(base_url: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{base_url}/nope")
    assert exc.value.code == 404
