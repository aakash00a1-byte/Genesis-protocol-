# Genesis V5 — Roadmap

Status per phase. Only functionality that exists and is tested is marked done.

| Phase | Scope | Status | Evidence |
|-------|-------|--------|----------|
| 1–3   | Kernel, Provider Fabric, Model Registry, Router, Agents, Permissions, Memory backend, OpenHands + Nemotron adapters, Reflection, offline tests | ✅ Done | `tests/unit/` |
| 4     | Memory Fabric (scopes, relevance, policies, sanitization, conflict, MemPalace boundary) | ✅ Done | `tests/unit/test_memory.py` |
| 5     | Agent Intelligence (planner, coordinator, 7 agents, DAG, retries) | ✅ Done | `tests/unit/test_coordinator.py` |
| 6     | Tool Fabric + secure execution (gateway + sandbox) | ✅ Done | `tests/unit/test_tools.py` |
| 7     | Provider/agent integrations (health, fallback, rate limits, normalization) | ✅ Done | `tests/integration/test_integrations.py` |
| 8     | Multi-agent + reflection + QA (independent verification) | ✅ Done | `tests/unit/test_reflection_qa.py` |
| 9     | Security + reliability + observability core | ✅ Done | `tests/unit/test_security.py` |
| 10    | Production readiness (config, Docker, health endpoints, shutdown, storage) | ✅ Done | `tests/unit/test_runtime.py` |
| E2E   | Complete offline integration scenario | ✅ Done | `tests/integration/test_end_to_end.py` |

## Done details

### Phases 1–3 foundation
- Kernel orchestration with memory → classification → routing → completion
  pipeline.
- Provider Fabric with offline MockProvider and a factory that can construct
  every adapter.
- Model Registry with capability-based lookup.
- Router with bounded fallback.
- Agent abstractions (Agent ABC, AgentTask, AgentResult, AgentRegistry).
- Tool permission model (RoleCatalog, PermissionSet, PolicyEngine).
- Memory backend abstraction.
- OpenHands SDK + NVIDIA Nemotron adapters (disabled until configured).
- Reflection engine.
- Offline tests for all of the above.

### Phase 4 — Memory Fabric
- `MemoryProvider`: read / write / search / list_scope / forget / clear.
- Scopes: session, task, project, long_term.
- Relevance filtering via `keyword_relevance` (Dice coefficient, offline).
- `MemoryWritePolicy` enforcement.
- Secret sanitization on write (redaction toggleable).
- Duplicate keys update in place; conflicts recorded in metadata without data
  loss.
- Graceful failure injection (recoverable).
- MemPalace adapter boundary: `MemPalaceAdapterContract`, `MemPalaceAdapter`
  (HTTP, disabled without config), `MemPalaceMock` (offline), factory
  `create_mempalace_adapter`.
- Kernel integration: `kernel.memory_write/read/search` +
  `Kernel.run` writes task memory.
- Tests: read, write, scope, relevance, duplicate, conflict, failure,
  sanitization, policy, MemPalace contract, Kernel integration. 26 tests.

### Phase 5 — Agent Intelligence
- Planner, AgentRegistry, AgentCoordinator (dependency-aware DAG execution,
  parallel-safe batches, result aggregation, bounded retries, failure
  recovery, circular-dependency rejection).
- Seven agents: CodingAgent, ResearchAgent, PlanningAgent, QAAgent,
  SecurityAgent, DeploymentAgent, MemoryAgent.
- Kernel remains the authority; the coordinator is wired via bootstrap.
- 18 tests in `tests/unit/test_coordinator.py`.

### Phase 6 — Tool Fabric + Secure Execution
- `ToolRegistry` / `ToolSpec` (identity, capability, schema, permission,
  risk level, invocation policy, timeout, audit).
- `Sandbox` boundaries (host access, credentials, destructive ops, hidden
  persistence, unauthorized network).
- `ToolGateway` — the only execution path for every category
  (browser/search/files/git/python/terminal/docker/apis).
- Built-in offline handlers; search/api/docker default-disabled.
- 27 tests in `tests/unit/test_tools.py`.

### Phase 7 — Provider/Agent integrations
- Adapters wired via config-based endpoints with pluggable HTTP transport.
- `ProviderTimeout` + wall-clock timeout helper; router catches timeouts.
- Provider health, bounded fallback, rate-limit handling, normalized
  responses and errors. Unconfigured providers stay DISABLED.
- 20 tests in `tests/integration/test_integrations.py`.

### Phase 8 — Multi-Agent + Reflection + QA
- `IndependentVerifier` (never marks producer work unquestionably correct),
  contradiction detection, quality scoring, bounded correction loop, failure
  escalation. Wired into Kernel pipeline + bootstrap.
- 18 tests in `tests/unit/test_reflection_qa.py`.

### Phase 9 — Security + Reliability + Observability
- `SecurityCore` zero-trust chokepoint (authenticate, authorize,
  rate-limit, validate in/out, redact, audit, track errors).
- `monitoring/` package — Metrics, health/readiness, ErrorTracker.
- PolicyEngine role helpers; hardened redactor (Authorization/Bearer,
  sk- prefixes); fixed `metrics.timed` decorator semantics.
- 27 tests in `tests/unit/test_security.py`.

### Phase 10 — Production readiness
- Configuration management with dev/test/prod separation via `GenesisConfig`
  + env parsing; no hard-coded credentials.
- Docker support: `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`
  (no secrets baked in).
- `runtime/` package: health/readiness endpoints, bounded worker pool,
  graceful shutdown, monitoring status.
- Memory persistence: snapshot/restore, JSON save/load (secrets redacted on
  disk), timestamped backups, recovery strategy.
- Structured logging (text/JSON, redacting formatter).
- 21 tests in `tests/unit/test_runtime.py`.

### End-to-End offline scenario
- `tests/integration/test_end_to_end.py` executes the full pipeline
  (User → Kernel → Memory → Classification → Planner → Router → Coordinator
  → Tool Permission → Sandbox → Execution → Reflection → QA → Memory Write →
  Audit) with zero network, zero credentials. 9 tests.

## Total test suite

248 tests collected; all pass (`python -m pytest tests/ -tb=no -q`).

## V6 — agent audit, auto-implement & verification

Post-V5 hardening, implemented only where a real gap was found in the code.

| Item | Scope | Status | Evidence |
|------|-------|--------|----------|
| Risk analysis | `RiskAnalyzer`: weighted signal scoring, level, recommendation, bounded escalation; advisory only | ✅ Done | `tests/unit/test_risk.py` |
| Alert boundary | `AlertNotifier` interface; default provider honest (`available=False`); undelivered alerts recorded | ✅ Done | `tests/unit/test_risk.py` |
| Agent tool mediation | Agents request tools via `Kernel.agent_tool_request`; bounded risk ceiling; no direct execution | ✅ Done | `tests/unit/test_agent_authority.py` |
| Kernel observability | Kernel wired to `Metrics` + `HealthRegistry`; `run()` records risk + counters; `health()` reports subsystems | ✅ Done | `tests/unit/test_agent_authority.py` |

## Not planned (out of scope for V5)

- Real external API verification from an offline environment — adapters stay
  DISABLED with clean boundaries until verified externally.
- Production deployment — explicitly out of scope. No deploy, no push.