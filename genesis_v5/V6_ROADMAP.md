# Genesis V6 Roadmap

Status: proposal. V5 is complete through Phase 10. This document lays out V6 as
a sequence of phases on top of the V5 foundation, in the same shape as the V5
build (each phase testable offline, each phase leaving the suite green).

## Guiding principles

1. **Generation is free; execution is governed.** The system may generate as
   many possibilities as it likes. Nothing acts on the world except through the
   authority layer (kernel policy, permissions, sandbox, audit).
2. **No hidden failures.** Every failure is recorded and surfaced
   (`genesis.transparency`).
3. **No blame, no spiral.** Failures are events, not verdicts; continuations
   are bounded (`genesis.resilience`).
4. **The human stays in authority.** The system supports and proposes; it does
   not decide for a person (`genesis.care`, `genesis.generation`).
5. **Honesty about capability.** When something is a simulation, it says so
   (`genesis.quantum.backends`).

## What already landed (V6 groundwork)

These were built ahead of the roadmap and are already in the suite:

- `genesis/transparency/` — decision ledger with expected-vs-actual benefit, and
  a failure ledger that reports `hidden_failures: 0`.
- `genesis/resilience/` — blame-free, bounded failure response.
- `genesis/care/` — a steady companion for overwhelmed users, with crisis
  referral to real human help.
- `genesis/quantum/` — a real statevector simulator (pure Python), plus honest
  backend detection for Qiskit/PennyLane/hardware.
- `genesis/generation/` — parallel, quantum-weighted candidate generation that
  produces proposals, never executable payloads.

## Phases

### Phase 11 — Generation service  ✅ DONE
- REST/webhook endpoint `/v1/generate` that accepts raw, unfiltered input and
  returns ranked proposals from `ParallelGenerator`.
- Accepts input verbatim; every response carries `requires_authority: true`.
- Zero dependencies (`http.server`); health/readiness/status endpoints included.
- Implemented in `genesis/service/http.py`; runnable via `genesis_serve.py`.

### Phase 12 — Authority gateway for proposals  ✅ DONE
- A single path (`AuthorityPipeline`) that takes a proposal and submits it
  through kernel policy, permissions, sandbox and audit before any tool runs.
- Rejections are recorded in the failure ledger with a reason, never silently
  dropped. `bypass_available` is always false.
- Implemented in `genesis/pipeline/authority.py`.

### Phase 13 — Quantum backends
- Optional Qiskit (Aer + IBM Quantum) and PennyLane adapters behind the existing
  `BackendInfo` interface.
- Hardware use requires a credential; without one the system reports
  `kind="simulator"` and never implies otherwise.
- Variational circuits for candidate scoring, evaluated on the simulator first.

### Phase 14 — Memory fabric integration
- Persist generation results and authority decisions into the memory fabric
  under the existing write policies (ALWAYS / VERIFIED / NEVER).
- Semantic search over past proposals, with provenance back to the decision id.

### Phase 15 — Reflection and thought-partner
- Reflection loop over generated candidates: critique, deduplicate, merge.
- A user-facing thought-partner mode built on `genesis.care` and
  `genesis.generation`: the system offers options and the user chooses.

### Phase 16 — Observability  ✅ DONE
- `/v1/status` exposes metrics (proposals generated, submissions, executions,
  denials) via `genesis.monitoring.metrics.Metrics`.
- `/healthz` and `/readyz` are live in the service layer.

### Phase 17 — Interfaces
- CLI and web surfaces wired to the generation and authority endpoints.
- Optional Telegram/Discord adapters, reusing the existing adapter layer.

## Non-goals (explicit)

These are deliberately out of scope, now and later:

- Any endpoint that executes raw input without passing through the authority
  layer.
- Any "bypass" switch that disables policy, permissions, sandbox or audit.
- Any claim of consciousness, or of activating or altering a person's mind.
- Presenting a classical simulation as quantum hardware.

## Definition of done per phase

- New code covered by unit tests.
- Full suite green (currently 199 tests).
- No phase weakens the authority layer or the transparency/resilience
  guarantees.
