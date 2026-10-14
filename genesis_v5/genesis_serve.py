#!/usr/bin/env python3
"""Run Genesis as a local HTTP service.

    python3 genesis_serve.py            # http://127.0.0.1:8000
    python3 genesis_serve.py 9000       # custom port

Then, in another terminal:

    curl -s localhost:8000/healthz
    curl -s -X POST localhost:8000/v1/generate \
        -H 'Content-Type: application/json' \
        -d '{"input":"raw !! input @#$ help me build a cache"}'

    curl -s -X POST localhost:8000/v1/submit \
        -H 'Content-Type: application/json' \
        -d '{"input":"list files","requests":[{"tool":"file.list","args":{"path":"/workspace"},"role":"coder","actor":"me","cwd":"/workspace"}]}'

Standard library only. No dependencies.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.bootstrap import build
from genesis.config.settings import Env, GenesisConfig
from genesis.generation.generator import ParallelGenerator
from genesis.pipeline.authority import AuthorityPipeline
from genesis.service.http import GenesisService, serve


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    kernel = build(GenesisConfig(env=Env.TESTING, offline=True))
    generator = ParallelGenerator(num_qubits=3, seed=None)
    pipeline = AuthorityPipeline(generator, kernel.gateway)
    service = GenesisService(
        generator,
        pipeline,
        status_provider=lambda: {"env": "testing", "offline": True},
    )
    print(f"Genesis service listening on http://127.0.0.1:{port}")
    print("  GET  /healthz  /readyz  /v1/status")
    print("  POST /v1/generate   POST /v1/submit   (gate is not optional)")
    print("Press Ctrl+C to stop.")
    try:
        serve(service, host="127.0.0.1", port=port)
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
