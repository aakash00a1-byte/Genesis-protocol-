# Audit — Stages 1–3, with evidence

**Date:** 2026-11-24 · **Baseline:** `main` @ `09dfa791` (PR #90 squash)
**Method:** read the code, run the suite, and probe the live Space. Every row
names the file and the test that backs the claim. A row with no test is marked
`partial` or `missing` — it is not called done because the code exists.

Rule used throughout: *code existing is not evidence; a passing test or a live
response is.*

---

## 1. Stage 1 — Foundation

| Claim | Evidence | Status |
|---|---|---|
| Fail-closed authorization | `agentic/policy.py` (`PRIVILEGED_OPERATIONS`, unknown tool/permission denied) · `test_agent_identity_trust.py`, `test_constitution.py` | **verified** |
| Owner approval gate on merges/deploys | `updates/github_prs.py` (evidence-bound merge), `scripts/patch_verification.py` · `test_gate_hardening.py`, `test_self_improve.py` | **verified** |
| Persistent memory with provenance | `agentic/memory.py` (`verify()` needs owner), `agentic/memory_safety.py` · `test_persistent_learning.py` | **verified** |
| Identity + trust | `agentic/identity_registry.py`, `agentic/trust.py` · `test_agent_identity_trust.py` (8 adversarial cases) | **verified** |
| Reasoning + planning (no execution) | `agentic/reasoning.py`, `agentic/planning.py`, `agentic/decision.py` · `test_reasoning_planning.py` | **verified** |
| Guardian (detect, propose, never act) | `guardian/*` · `test_guardian_selfdefence.py`, `test_guardian_defence.py` | **verified** |
| Bounded autonomy | `bounded/*` (budget, rate limit, runaway, governor) · `test_bounded_autonomy.py` | **verified** |
| Recovery | `recovery/*` (encrypted, verified restore) · `test_recovery.py` | **verified** |
| Auditable change history | `agentic/audit.py`; tamper-evident `guardian/events.py`; `research/ledger.py` (new) | **verified** |
| Single CLI execution gate | `tools/cli_guard.py` + `tools/cli_policy.py` · `test_cli_gate_skills.py::test_no_product_module_starts_a_process_outside_the_gate` | **verified** (this audit added `research/benchmark.py` to it) |

**Finding (fixed):** `/api/infinity/status` published fabricated progress — a
hardcoded 60/40/20/0/0/0 milestone set plus an auto-updater that recomputed
"progress" from elapsed calendar time since 2024-01-01. Live probe on
2026-11-24 returned `average_progress: 87.7` with `completed_milestones: 0`,
`total_interactions: 0`, `learnings_count: 0`. It also listed a
`consciousness / "Self-Awareness"` milestone.

Fixed in `genesis_protocol/infinity/future_roadmap.py` + `auto_updater.py`:
progress is now `0 / 50 / 100` derived from recorded evidence, the setter is
refused, stale numbers on disk are ignored on load, and the self-awareness
milestone is gone. Regression: `tests/test_infinity_honesty.py` (12 tests).

## 2. Stage 2 — Multi-AI integration

| Claim | Evidence | Status |
|---|---|---|
| Multi-provider chain with fallback | `ai/provider_chain.py` · `test_providers.py`, `test_provider_loop_safety.py` | **verified** |
| Task-based model selection | `ai/scoring_engine.py` · `test_scoring.py` | **verified** |
| Free-tier-first resource policy | `ai/providers/*` (groq/gemini/mistral/nvidia/orcarouter), `integrations/key_free_search.py` | **verified** |
| Per-model output recorded | `CouncilResult.members`, audit log | **verified** |
| Model capability registry | `ai/scoring_engine` capability data | **partial** — selection is score-based, not capability-declared |

## 3. Stage 3 — Collective intelligence

| Claim | Evidence | Status |
|---|---|---|
| BEST / VOTE / SYNTHESIS | `ai/council.py` · `test_council.py` (12) | **verified** |
| Correlated-error detection | `ai/independence.py` (new): provider families, aggregator discount, source overlap, `is_evidence` always `False` · `test_council_independence.py` (11) | **new — verified** |
| Consensus never treated as truth | `CouncilResult.independence.is_evidence == False`; constitution article 4 | **verified** |
| Individual identity + narrowed delegation | `coordination/registry.py`, `coordination/tasks.py`, `agentic/identity_registry.py` · `test_coordination.py` | **verified** |
| Signed agent messaging | `coordination/messaging.py` (HMAC over sender credential, replay set) · `test_coordination.py` | **verified** |
| Cross-interface consistency | `coordination/interfaces.py` · `test_coordination.py` | **verified** |
| AI-to-AI debate | — | **missing** |
| Cross-model fact checking against sources | — | **missing** (only independence is measured, not correctness) |
| Evidence-based disagreement resolution | — | **partial** — disagreement is now *detected* and flagged, not resolved |

The honest summary of Stage 3: the council can tell you *whether* an agreement
is worth anything. It cannot yet tell you *which* member is right, because that
needs a source of truth the models do not share — which is Stage 4's job.

## 4. Stage 4 — Scientific research engine (foundation, this change)

| Claim | Evidence | Status |
|---|---|---|
| Ordered cycle with evidence gates | `research/cycle.py` (`STAGES`, `REQUIRED`, refuse to skip) · `test_research_cycle.py` | **new — verified** |
| Verification must be independent and passing | `ResearchCycle._require_independent_check` (also refuses a producer verifying itself) · `test_a_producer_cannot_verify_itself` | **new — verified** |
| No report/claim without a verified result | `can_claim_discovery()` · `test_report_requires_a_verified_result` | **new — verified** |
| Negative results kept permanently | `research/hypothesis.py` (refuted is terminal, no delete), `research/ledger.py` (append-only, hash-chained) · `test_a_refuted_hypothesis_is_permanent`, `test_the_ledger_detects_tampering` | **new — verified** |
| Reproducible first benchmark | `research/benchmark.py`: 13 propositional problems incl. 3 negative controls, exhaustive truth tables · `test_research_benchmark.py` | **new — verified** (13/13, checker discriminating) |
| Lean formal proofs | `LeanChecker` — adapter present, routed through the CLI gate, reports `available: False` here | **missing by environment** — no Lean binary; **no Lean result is claimed** |
| Hypothesis generation / experiment execution | — | **missing** (the cycle *gates* work; it does not do the work) |

## 5. Long-term mission

`docs/RESEARCH_MISSION.md` converts the constitution's research ambitions
(time, space, matter, molecules, reality) into the falsifiable-question format
the cycle requires. It contains questions, not answers, and says so.

## 6. What this audit did not do

- It did not run Lean, and it does not claim to have.
- It did not generate hypotheses or run experiments.
- It did not merge, deploy, change a secret or push `main`.
- It did not re-audit the V6 kernel in `genesis_v5/` beyond running its suite.
