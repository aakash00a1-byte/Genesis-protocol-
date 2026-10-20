#!/usr/bin/env python3
"""Run Genesis against a real LLM provider.

    python3 genesis_live.py "say hello in one sentence"

Keys are read from the environment. If a ``.env`` file sits next to this
script it is loaded first (KEY=VALUE lines, ``#`` comments) so you do not have
to export anything by hand. The key is never printed.

Which provider is used depends on what you configure; the first healthy one in
this order wins (see ``genesis/models/registry.py``):

    openai_compat · claude · gemini · nemotron · local · openhandssdk

Examples:

    # Any OpenAI-compatible endpoint (OpenRouter, Groq, Together, DeepSeek...):
    GENESIS_OPENAI_COMPAT_BASE_URL=https://api.groq.com/openai/v1
    GENESIS_OPENAI_COMPAT_API_KEY=<your-key>
    GENESIS_OPENAI_COMPAT_MODEL=llama-3.3-70b-versatile

    # Anthropic:
    ANTHROPIC_API_KEY=<your-key>          # GENESIS_CLAUDE_MODEL optional

    # Google:
    GENESIS_GEMINI_API_KEY=<your-key>     # GENESIS_GEMINI_MODEL optional

    # Local (no key):
    GENESIS_LOCAL_BASE_URL=http://localhost:11434/v1

Set GENESIS_OFFLINE=false so the router is allowed to reach a live provider.
Standard library only.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.adapters.registration import register_default_adapters
from genesis.bootstrap import build
from genesis.config.settings import GenesisConfig
from genesis.providers.base import ModelCapability
from genesis.providers.factory import get_factory

_LIVE_ORDER = ("openai_compat", "claude", "gemini", "nemotron", "local", "openhandssdk")


def load_dotenv(path: Path) -> int:
    """Load KEY=VALUE lines from ``path`` without overriding real env vars."""
    if not path.is_file():
        return 0
    loaded = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    loaded = load_dotenv(here / ".env")
    if loaded:
        print(f"loaded {loaded} value(s) from .env")

    # A live provider needs offline=False.
    if os.getenv("GENESIS_OFFLINE") is None:
        os.environ["GENESIS_OFFLINE"] = "false"
    cfg = GenesisConfig.from_env()
    register_default_adapters()
    factory = get_factory()

    print("provider health:")
    healthy: list[str] = []
    for name in _LIVE_ORDER:
        try:
            health = factory.health(name, cfg)
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<14} error: {exc}")
            continue
        marker = "ok " if health.ok else "-- "
        print(f"  {marker}{name:<14} {health.status.value}: {health.message}")
        if health.ok:
            healthy.append(name)

    if not healthy:
        print("\nno live provider is configured. Add a key to .env (see the")
        print("header of this file) or export one, then run again.")
        return 1

    prompt = " ".join(argv[1:]) or "In one sentence, what is Genesis V5?"
    kernel = build(cfg)
    print(f"\nprompt: {prompt!r}")
    result = kernel.complete(prompt, ModelCapability.CHAT, offline=False)
    print(f"provider : {result.provider}")
    print(f"model    : {result.model}")
    print(f"latency  : {result.latency_ms} ms")
    print(f"output   : {result.output}")

    if cfg.autonomy.enabled:
        from genesis.autonomy import AutonomousLoop

        loop = AutonomousLoop(kernel, cfg.autonomy)
        run = loop.run(prompt, actor="live", role=cfg.integration.default_role)
        print(f"\nautonomy : {run.status.value} (iterations={run.iterations})")
        print(f"result   : {run.result or '(no result)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
