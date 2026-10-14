# AGENTS.md — Genesis V5

Repository memory for agents working in this workspace.

## Project

Genesis V5 is a Kernel-orchestrated multi-agent AI system. It runs fully
offline by default. No credentials are required for tests. Real provider
adapters stay disabled unless configured via environment variables.

## Commands

```bash
# Install (dev + offline deps)
pip install -e ".[dev]"

# Run the whole test suite
python -m pytest tests/ -tb=no -q

# Run only integration/offline E2E
python -m pytest tests/integration/ -q

# Single file
python -m pytest tests/unit/test_memory.py -q
```

## Layout

- `genesis/kernel/` — `GenesisKernel`, the authority.
- `genesis/memory/` — Memory Fabric (`MemoryProvider`, `MemPalace*`) +
  snapshot/restore/backup persistence.
- `genesis/providers/`, `genesis/adapters/` — Provider Fabric + adapters.
- `genesis/models/`, `genesis/router/` — Model Registry + Router.
- `genesis/agents/`, `genesis/coordinator/`, `genesis/planning/` — Agent
  base, registry, coordinator, planner, built-in agents.
- `genesis/tools/` — Tool Registry, Sandbox, Tool Gateway.
- `genesis/security/` — SecurityCore, permissions, audit, redaction, rate
  limit, validation.
- `genesis/reflection/`, `genesis/qa/` — bounded reflection + independent
  verifier.
- `genesis/monitoring/` — Metrics, health/readiness, ErrorTracker.
- `genesis/runtime/` — ApplicationRuntime, WorkerPool, graceful shutdown.
- `genesis/logging/` — structured logging setup (text/JSON, redacting).
- `genesis/config/` — GenesisConfig sections + env separation.
- `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh` — no secrets
  baked in; runtime secrets via environment.
- `tests/unit/`, `tests/integration/` — offline test suite.

## Storage / persistence

- MemoryProvider supports `snapshot()/restore()`, `save_to()/load_from()`
  (JSON, secrets redacted on disk), and `backup()` (timestamped).
- Configure via `GenesisConfig.storage` (`StorageConfig`); `save_to()` file
  lives under `storage.data_dir`.

## Conventions

- Do not modify existing tests to hide failures; distinguish pre-existing
  failures from regressions.
- Never commit secrets; never print API keys/tokens.
- Only document functionality that exists and is tested.
- Checkpoint commits after each phase: `v5-phase-N-<name>`.
- Do not push; do not deploy.
- External APIs that cannot be verified → clean adapter boundary + offline
  mock only. Never invent an external API.
- No infinite retry/fallback loops anywhere (bounded policies only).

## Build order (phases)

Foundation (kernel/providers/registry/router/agents/permissions/memory/
adapters/reflection/offline tests) → 4 Memory Fabric → 5 Agent Intelligence
→ 6 Tool Fabric + Secure Execution → 7 Provider Integration → 8 Multi-Agent +
Reflection + QA → 9 Security/Reliability/Observability → 10 Production
Readiness → offline E2E scenario.

## Verification loop (per phase)

1. inspect `git diff`
2. run relevant tests
3. run full suite: `python -m pytest tests/ -tb=no -q`
4. verify no secrets (`git diff | grep -i -E "api[_-]?key|token|secret="`)
5. commit checkpoint
6. continue only if safe and tests acceptable