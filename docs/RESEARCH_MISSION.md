# Research mission — falsifiable questions, not answers

The constitution asks for research on time, space, matter, molecules and
reality. Those are directions, not questions: a direction cannot be answered,
falsified or reproduced, so it cannot be science yet.

This document is the bridge. Each direction is converted into the format
`genesis_protocol/research/cycle.py` requires:

```
question          - one sentence, answerable
why_it_matters    - what changes if the answer is one way or the other
falsifiable_test  - the measurement that would settle it
model             - the formalism the prediction is made in
prediction        - what the model says will happen, stated in advance
```

A direction that cannot be written in this shape stays on the "not yet
researchable" list. That list is a feature: it is the honest boundary of what
this system can currently approach.

## Why this ordering

The engine can only verify what it can check mechanically. So the questions are
ordered by *how cheaply they can be settled*, not by how interesting they sound:

1. **Formal questions** — a proof checker decides them. Cheap, certain, no
   instrument. (This is where `research/benchmark.py` starts.)
2. **Computational questions** — a simulation decides them, given a stated model
   and a reproducibility check on the same inputs.
3. **Empirical questions** — a measurement decides them, which needs an
   instrument and a human. Stage 5 territory.

A question that needs an instrument is not refused; it is *parked* with the
instrument it needs named, so nobody mistakes "we have not measured it" for "we
have shown it".

## Researchable now (formal, checker-decided)

| Question | Falsifiable test | Status |
|---|---|---|
| Is Peirce's law derivable in classical propositional logic? | exhaustive truth table | **answered** — tautology, `research/benchmark.py` |
| Are the De Morgan identities valid classically but not intuitionistically? | truth table (classical) + a counter-model search (intuitionistic) | **partial** — classical half answered; intuitionistic half needs a checker that models Kripke semantics |
| Which of the 13 benchmark statements fail, and why? | independent checker with negative controls | **answered** — all controls rejected; see benchmark output |
| Can a Lean 4 proof be produced and checked for each benchmark statement? | `lean` exit code 0 on a generated proof file | **parked** — no Lean binary in this environment |

## Parked (needs a model or an instrument this system does not have)

| Question | What would settle it | Blocker |
|---|---|---|
| Does the current best-fit cosmological model predict a measurable deviation from general relativity at galactic scales? | comparison against published rotation-curve data | needs a dataset and a numerical model; not a checker problem |
| Is there a stable molecular configuration at pressure P that is not in the published phase diagram? | DFT or MD simulation, reproduced twice | needs a simulation stack and compute budget (owner approval) |
| Does the observed value of a fundamental constant drift measurably over the observation window? | instrument time series with stated error bars | needs an instrument; Stage 5 |

## Rules for adding a question

1. One sentence. If it needs "and", it is two questions.
2. The falsifiable test must be runnable *before* the answer is known.
3. The prediction must be written down before the test runs, and the ledger
   (`research/ledger.py`) records it with a timestamp and a hash.
4. A refuted hypothesis stays in the book forever (`research/hypothesis.py`).
5. A "discovery" needs a written report *and* an independent passing check
   (`ResearchCycle.can_claim_discovery()`). Publishing it is a privileged
   operation — owner approval, always.

## What this document is not

It is not a claim that Genesis has made, or is close to making, a scientific
discovery. It is the list of questions it is set up to ask, and the honest
statement of which of them it can currently answer.
