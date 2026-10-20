#!/usr/bin/env python3
"""Run the Discord/Telegram integration for Genesis.

    python3 genesis_integrations.py

Off by default and refuses everything until it is told which channels it may
answer. Configure with:

    GENESIS_INTEGRATION_ENABLED=true
    GENESIS_INTEGRATION_ALLOWED_CHANNELS=<discord-channel-id>,<telegram-chat-id>
    GENESIS_DISCORD_ENABLED=true   DISCORD_BOT_TOKEN=...
    GENESIS_TELEGRAM_ENABLED=true  TELEGRAM_BOT_TOKEN=...

Commands a chat room may use:

    /generate <input>   proposals only, no side effects
    /task <task>        a bounded autonomous run (needs autonomy enabled)
    /submit <input>     offers tool requests to the authority gate

Every message is scanned by the guard, parsed into a command, and routed
through the same gate and loop as any other request. Nothing is executed raw.
Standard library only.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from genesis.bootstrap import build, build_chat_gateway
from genesis.config.settings import GenesisConfig
from genesis.integration.runner import build_runners


def main() -> int:
    cfg = GenesisConfig.from_env()
    kernel = build(cfg)
    gateway = build_chat_gateway(kernel, config=cfg)

    if not cfg.integration.enabled:
        print("integration is OFF (set GENESIS_INTEGRATION_ENABLED=true).")
        print("  channels : (none configured)")
        print("  nothing is running; the gate is untouched.")
        return 0

    runners = build_runners(cfg.integration, gateway)
    print("Genesis chat integration")
    print(f"  allowed channels : {cfg.integration.allowed_channels or '(none — refuses all)'}")
    print(f"  default role     : {cfg.integration.default_role}")
    print(f"  autonomy wired   : {gateway.loop is not None}")
    if not runners:
        print("  no transport configured (set a token and *_ENABLED=true).")
        return 0
    for runner in runners:
        print(f"  started : {runner.name}")
        runner.start()
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for runner in runners:
            runner.stop()
        print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
