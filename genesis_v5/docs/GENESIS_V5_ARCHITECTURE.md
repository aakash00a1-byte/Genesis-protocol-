# Genesis V5 — Architecture

This document describes only functionality that exists and is tested.

## Overview

```
User Task
   ↓
Genesis API
   ↓
Genesis Kernel
   ↓
Memory Retrieval → Memory Fabric (scoped, policy-controlled, sanitized)
Task Classification
Risk Analysis (offline, advisory) -> level + recommendation (+ alert boundary)
   ↓
Planner → Subtasks → Agent Registry → Dependency Graph → parallel execution
   ↓
Model Router (capability → best provider → bounded fallback)
   ↓
Tool Permission + Sandbox (Tool Gateway)
   ↓
Agent Execution
   ↓
Bounded Reflection
   ↓
Independent QA
   ↓
Memory Write (policy-controlled)
   ↓
Final Result
   ↓
Audit Event
```

## Components

### Kernel (`genesis/kernel/`)
- `GenesisKernel` orchestrates the pipeline. It is the only authority for
  memory, model routing, tool execution, and agent coordination.
- `KernelRequest` / `KernelResponse` are the unit of work.

### Memory Fabric (`genesis/memory/`)
- `MemoryProvider` — scoped store (session/task/project/long-term) with
  relevance filtering, secret sanitization, duplicate/conflict handling, and
  graceful failure.
- `MemoryWritePolicy` — ALWAYS / ON_SUCCESS / ON_FAILURE / NEVER / VERIFIED.
- `ProviderMemoryAdapter` — clean boundary for external backends.
- `MemPalaceAdapter` / `MemPalaceAdapterContract` / `MemPalaceMock` — MemPalace
  boundary; the real HTTP adapter is disabled unless an endpoint + API key are
  configured. Only the contract is stable; the wire format is unverified.

### Model Providers (`genesis/providers/`, `genesis/adapters/`)
- `Provider` ABC with normalized `health()`, `capabilities()`, `complete()`.
- `ProviderFactory` registry.
- `MockProvider` — offline, always available.
- Adapters: OpenHands SDK, NVIDIA Nemotron, OpenAI-compatible, Gemini, Claude,
  Local (Ollama-compatible). All are **DISABLED** until configured.

### Router (`genesis/router/`)
- `ModelRouter` — capability analysis → available models → cost/latency/
  reliability → best provider → bounded fallback. No infinite loops.

### Agent layer (`genesis/agents/`)
- `Agent`, `AgentTask`, `AgentResult`, `AgentRegistry`.
- Phase 5 adds planner, coordinator, dependency DAG, and the seven agents.
- Tool mediation: an agent never executes a tool. It asks
  (`Agent.request_tool`); the coordinator binds a Kernel-mediated gateway
  (`Kernel.agent_tool_request`) so the request travels the same authority
  gate, with the run's actor/role and a bounded risk ceiling (MEDIUM default).
  An agent with no gateway bound reports `no_gateway` instead of executing.

#### Registered agents (8)

All are offline `_DeterministicAgent` subclasses: they produce a deterministic
`[verb] instruction` string and carry no provider dependency of their own.
They reach tools only through the Kernel gateway, and only when the *task*
declares one (`metadata={"tool": ..., "args": {...}}`); an agent cannot invent
a tool call.

| Agent | Verb | Selected for | Typical tools (via gate) |
|-------|------|--------------|--------------------------|
| `planning` | planned | `plan`/`design`/`architecture` | none by default |
| `research` | researched | `research`/`search`/`investigate` | `search.web`, `file.read` |
| `coding` | implemented | `code`/`implement`/`refactor` | `file.read`, `file.write`, `git.*` |
| `qa` | verified | `test`/`verify`/`qa` | `file.read`, `python.run` |
| `security` | security-reviewed | `security`/`audit`/`threat` | `file.read` |
| `deployment` | prepared | `deploy`/`release`/`package` | none by default |
| `memory` | memorized | always (final step) | none by default |
| `generic` | processed | any unmapped label | none by default |

Provider dependency: none. Real model providers stay disabled unless
configured by environment variables (see `genesis/providers/`).

### Risk (`genesis/risk/`)
- `RiskAnalyzer` — scores a task's risk from explicit, weighted signals
  (destructive, credential access, network, privilege, secret-like, size),
  escalates one level for high-impact actions, and returns a recommendation.
  Offline and advisory: it informs the Kernel, it never bypasses the gate.
- `AlertNotifier` boundary — the default `NoAlertProvider` reports
  `available=False` and never fabricates delivery; an undelivered alert at or
  above threshold is recorded in the failure ledger.
- Scope honesty: this module scores the text it is given. It does not fetch
  external disaster feeds and does not deliver notifications. Those require a
  real, verified provider plugged into `AlertNotifier`, and that has not been
  configured or tested here.

### Tool Fabric (`genesis/tools/`)
- `ToolRegistry` — every tool declares identity, capability, schema,
  permission, risk level, invocation policy, timeout.
- `Sandbox` — blocks credential access, destructive ops, unauthorized
  network access, persistence, and paths outside the sandbox root.
- `ToolGateway` — the only execution path: Policy Check → Permission Gate →
  Sandbox → Execute → Result → Audit. No model or agent calls tools directly.

### Security Core (`genesis/security/`)
- Roles/permissions (`RoleCatalog`, `PolicyEngine`) — zero-trust.
- `SecurityCore` — zero-trust chokepoint: authenticate → authorize →
  rate-limit → validate in/out → redact → audit → error tracking.
- `Redactor` — secret redaction (Bearer/Authorization, sk- prefixes).
- `AuditLogger` — structured, redacted audit events.
- `RateLimiter` — sliding window.
- `validate_input` / `validate_output` — size, shape, injection heuristics.

### Runtime (`genesis/runtime/`)
- `ApplicationRuntime` — health/readiness endpoints, bounded worker pool
  (start/submit/drain/stop), graceful shutdown hooks, monitoring status.
- `RuntimeHealth` — liveness + readiness checks; readiness degrades before
  startup completes.
- `WorkerPool` — bounded queue + worker threads, refuses work after stop or
  when full (resource limits).

### Persistence (`genesis/memory/provider.py`)
- Snapshot / restore, JSON save / load (secrets redacted on disk), and
  timestamped backups for the Memory Fabric.

### Logging (`genesis/logging/`)
- `logging_setup` — text/JSON structured logging, redacting formatter,
  configurable level/format/file.

### Observability (`genesis/monitoring/`)
- `Metrics` — counters, histograms, and a fixed `timed` decorator factory.
- `ErrorTracker` — structured error capture.
- Health/readiness streams from the runtime layer.

### Configuration (`genesis/config/`)
- `GenesisConfig` sections: memory, router, tools, agents, security,
  storage, logging, runtime. Environment separation via `Env`
  (development/testing/production) and env-var overrides.

### Docker (`Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`)
- Offline-capable image; runtime secrets come from environment, never baked
  in. Compose template documents provider env keys without supplying values.

### Reflection (`genesis/reflection/`)
- `ReflectionEngine` — bounded reflection, contradiction detection, quality
  scores, confidence metadata.

### Independent QA (`genesis/qa/`)
- `IndependentVerifier` — never marks producer work as unquestionably
  correct; contradiction detection, result quality scoring, bounded
  correction loop, failure escalation. Wired into Kernel pipeline.

## Security model

- No model, agent, tool, or provider gets implicit authority.
- Everything is explicitly permitted by `RoleCatalog` + `PermissionSet`
  (zero trust).
- Audit events: types `kernel.run`, `tool_exec`, `tool_denied`,
  `sandbox_violation`, `memory_write`, `memory_read`, etc.
- Secrets never enter code; they resolve via `resolve_secret` and are
  redacted in every sink.

## Status legend

- **IMPLEMENTED** — code exists.
- **TESTED** — covered by the offline test suite.
- **INTEGRATED** — wired into the Kernel pipeline and validated.
- **UNVERIFIED** — external API not verified from offline environment;
  adapter boundary + offline mock only.