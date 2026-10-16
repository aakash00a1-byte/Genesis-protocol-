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
- `genesis/risk/` — `RiskAnalyzer`: scores task risk (offline, advisory),
  recommends a response, and holds the (opt-in) alert-notifier boundary.
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

## Session recovery (read this first in a new session)

Work is on branch `genesis-v5-recovered`, pushed to
`https://github.com/aakash00a1-byte/Genesis-protocol-.git`. Recovery is from
git: `git fetch origin && git checkout genesis-v5-recovered`. Do not rely on a
previous chat transcript; the branch is the source of truth.

### Runnable entry points

```bash
python3 genesis_test.py "<raw input>"   # proposals + the authority gate
python3 genesis_quantum.py              # Grover, QFT, Deutsch-Jozsa, CHSH
python3 genesis_chat.py                 # interactive thought-partner
python3 genesis_serve.py 8000           # HTTP service (/v1/generate, /v1/submit)
```

### Layers added on top of phases 4-10

- `genesis/transparency/` — decision + failure ledger; no hidden failures.
- `genesis/resilience/` — learn from failure without blame.
- `genesis/care/` — STEADY / REFRAME / crisis referral; wired into the kernel.
- `genesis/risk/` — `RiskAnalyzer` scores task risk and recommends a response.
  Advisory only: it informs the Kernel, it never bypasses the gate. The alert
  notifier reports `available=False` until a verified provider is wired; an
  undelivered alert at/above threshold is recorded in the failure ledger, not
  hidden.
- `genesis/quantum/` — pure-Python complex statevector simulator, honest
  backend detection, optional Qiskit/PennyLane adapters, and real algorithms
  (`algorithms.py`: Grover, QFT, Deutsch-Jozsa, CHSH).
- `genesis/generation/` — parallel proposal generation; `quantum_rank.py` ranks
  candidates by Grover amplitude amplification.
- `genesis/pipeline/` — `AuthorityPipeline`: raw input -> policy -> action.
- `genesis/service/` — zero-dependency HTTP service (stdlib `http.server`).
- `genesis/reflection/partner.py` — thought-partner: offers options, the user
  chooses; crisis turns offer none and refer to human help.

### Invariants that must not be broken

- Proposals never execute on their own. `bypass_available` is always false.
- Agents never execute a tool directly. An agent *asks*; the request travels
  the Kernel's authority gate (`Kernel.agent_tool_request`) with the run's
  actor/role, under a bounded risk ceiling (MEDIUM by default).
- Every denial is recorded with a reason and surfaced, never dropped.
- No hidden failures. No blame language in resilience or care output.
- The thought-partner never decides for the user (`decided_for_user == 0`).
- Quantum claims stay honest: a simulator is labelled a simulator; hardware
  requires a credential. Grover ranking is not described as a speedup.

### Pushing

The default `GITHUB_TOKEN` is read-only (`contents=read`) and will 403 on push.
A write-scoped token must be supplied explicitly for the push only. Never
commit a token; never print one.
