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
- `genesis/models/`, `genesis/router/` — Model Registry + Router. A configured
  provider is registered into the catalog by `default_registry(cfg)` only when
  it reports healthy; an unconfigured adapter is absent (never fabricated).
  The offline mock stays as the last-resort fallback (low reliability).
- `genesis/agents/`, `genesis/coordinator/`, `genesis/planning/` — Agent
  base, registry, coordinator, planner, built-in agents.
- `genesis/tools/` — Tool Registry, Sandbox, Tool Gateway.
- `genesis/security/` — SecurityCore, permissions, audit, redaction, rate
  limit, validation.
- `genesis/reflection/`, `genesis/qa/` — bounded reflection + independent
  verifier.
- `genesis/risk/` — `RiskAnalyzer`: scores task risk (offline, advisory),
  recommends a response, and holds the (opt-in) alert-notifier boundary.
  Scoring only — it does not fetch external disaster data and does not
  deliver notifications (no verified provider is wired).
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

> V6 note: commit `feat(v6): risk analysis + agent tool mediation + kernel
> observability` may exist **locally only** if the available token was
> read-only. Check `git log origin/genesis-v5-recovered..HEAD` and push it
> before continuing. Never commit or print a token.

### Runnable entry points

```bash
python3 genesis_test.py "<raw input>"   # proposals + the authority gate
python3 genesis_quantum.py              # Grover, QFT, Deutsch-Jozsa, CHSH
python3 genesis_chat.py                 # interactive thought-partner
python3 genesis_serve.py 8000           # HTTP service (/v1/generate, /v1/submit)
python3 genesis_autonomy.py "<task>"    # bounded autonomous loop (V6)
```

### Agent inventory & verified workflows (V6 audit)

Verified against the running code, not the roadmap.

Agents (8, all offline, no provider dependency): `planning`, `research`,
`coding`, `qa`, `security`, `deployment`, `memory`, `generic`. Each is a
`_DeterministicAgent`; selection is keyword-based in `TaskDecomposer` ->
`Planner`. `memory` is always the final step. See the architecture doc for the
full table (verb, selection keywords, typical tools).

Execution path (verified end to end in
`tests/integration/test_multi_agent.py`):
`Kernel.run` -> memory retrieval -> classification -> risk analysis ->
`AgentCoordinator.run_task` (seeds the task context) -> `Planner.plan` ->
per-level bounded-parallel `_run_step` -> agent -> `Kernel.agent_tool_request`
-> ToolGateway (policy -> permission -> sandbox -> execute -> audit) ->
reflection -> independent QA -> memory write (redacted) -> audit.

Verified capabilities:
- Role-based denial on the agent path (e.g. `researcher` cannot `file.write`).
- Risk ceiling: the agent path defaults to MEDIUM; `terminal.run` (HIGH) is
  denied even for `admin` unless the caller raises `max_risk` explicitly.
- Tool failure and timeout are surfaced to the caller and audited
  (`tool_failure` / `tool_timeout`), never hidden.
- Bounded retries: `RetryLimitExceeded` after `max_retries`; no infinite loop.
- Deterministic ordering: parallel-level results are emitted in plan order and
  the first error is chosen deterministically.
- QA rejection: failure markers / empty results fail verification and are
  recorded in the failure ledger.
- Memory isolation: scopes are isolated; secrets are redacted in strings
  *and* structured (dict/list) values before persistence.
- Sandbox path checks resolve symlinks (`os.path.realpath`), so a link placed
  inside the allowed root cannot be used to read a target outside it
  (`tests/unit/test_tools.py::test_sandbox_blocks_symlink_escape`).

Limitations (do not overstate):
- The risk module scores risk only. It does not pull external disaster data
  and does not deliver alerts; the default notifier reports
  `available=False` and an undelivered alert at/above threshold is recorded,
  not sent.
- Agents are deterministic offline stubs. Real model providers are disabled
  unless configured by environment variables. When configured (e.g.
  `GENESIS_OPENAI_COMPAT_BASE_URL` + `GENESIS_OPENAI_COMPAT_API_KEY`), the
  provider enters the catalog and an online run routes to it; the offline
  default still resolves to the mock.
- No deployment. Push requires a write-scoped token that is not available here.

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
- `genesis/autonomy/` — **bounded autonomous engineering loop (V6)**. A
  controller that drives the existing Kernel; it adds no new execution path.
  Off by default (`AutonomyConfig.enabled`, env `GENESIS_AUTONOMY_ENABLED`).
  Bounded by `max_iterations`, `max_retries_per_step`, `max_wall_clock_seconds`,
  `step_timeout_seconds`. `guard.py` refuses forbidden actions (push, deploy,
  publish, credential edits, disabling security) and prompt-injection markers
  before any agent runs, and refuses unsafe tools (`docker.exec`,
  `terminal.run`, `api.call`, `search.web`). `state.py` checkpoints each run
  atomically to disk and redacts secrets on the way; `FAILED` runs stay
  resumable, `SUCCEEDED`/`BLOCKED` are terminal. `acceptance.py` is a
  tests+security gate: a change is only accepted once its secret scan and
  (optionally injected) test run pass.

### Autonomous loop invariants (V6)

- The loop only calls `Kernel.run`; every tool call still travels the Tool
  Gateway (policy -> permission -> sandbox -> execute -> audit).
- A run is never reported as `ok` unless it produced a non-empty verified
  result and (when a gate is wired) passed the acceptance gate. No false
  success.
- A single iteration is bounded by `step_timeout_seconds`; a hung step is cut
  off, not waited on. The loop always terminates within its bounds.
- Forbidden actions and injected instructions are refused *before* any agent
  sees the task, and the refusal is audited.
- Checkpoints are atomic and redacted; a secret in a task never reaches disk.

### Invariants that must not be broken

- The autonomy loop (V6) is bounded and off by default; see "Autonomous loop
  invariants" above.
- Proposals never execute on their own. `bypass_available` is always false.
- The gate is never removed. There is no `bypass_gatekeeper`. The only
  relaxation is a bounded standing grant (`SecurityConfig.auto_grant_*`,
  empty by default): it fires only when the actor AND a listed permission AND
  the LOW risk ceiling all agree, so it can never reach a write or a
  HIGH/CRITICAL tool. Denials are still audited.
- Agents never execute a tool directly. An agent *asks*; the request travels
  the Kernel's authority gate (`Kernel.agent_tool_request`) with the run's
  actor/role, under a bounded risk ceiling (MEDIUM by default).
- Every agent receives the originating task in `AgentTask.context` (seeded by
  `AgentCoordinator.run_task`); agents never run context-free.
- Parallel-level results are emitted deterministically in plan order.
- Secrets are redacted in strings *and* inside structured memory values;
  `secret_redacted` never claims a redaction that did not happen.
- Every denial is recorded with a reason and surfaced, never dropped.
- No hidden failures. No blame language in resilience or care output.
- The thought-partner never decides for the user (`decided_for_user == 0`).
- Quantum claims stay honest: a simulator is labelled a simulator; hardware
  requires a credential. Grover ranking is not described as a speedup.

### Pushing

The default `GITHUB_TOKEN` is read-only (`contents=read`) and will 403 on push.
A write-scoped token must be supplied explicitly for the push only. Never
commit a token; never print one.
