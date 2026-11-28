"""Stage 4 foundation: a research cycle that cannot skip verification.

The pieces:

* ``ledger``      - append-only, hash-chained record of everything, failures included
* ``hypothesis``  - falsifiable claims; supported needs an independent check,
                    refuted is permanent
* ``cycle``       - ordered stages with evidence gates; no report without a
                    verified result
* ``benchmark``   - a reproducible propositional-logic benchmark with negative
                    controls, plus a Lean adapter that reports ``unavailable``
                    when Lean is not installed instead of claiming a result

What this package is not: a discovery engine. It does not generate hypotheses,
run experiments or call models. It decides whether the evidence on hand is
enough to advance, and refuses when it is not. That refusal is the feature - a
research pipeline that cannot say "not verified" cannot produce a discovery, only
a claim.

Stdlib only.
"""
from .benchmark import (
    CONTINGENT,
    CONTRADICTION,
    PROBLEMS,
    TAUTOLOGY,
    LeanChecker,
    Problem,
    TruthTableChecker,
    classify,
    run_benchmark,
)
from .cycle import (
    STAGES,
    MissingEvidenceError,
    ResearchCycle,
    ResearchError,
    StageOrderError,
    VerificationRequiredError,
)
from .hypothesis import (
    REFUTED,
    SUPPORTED,
    Hypothesis,
    HypothesisBook,
    HypothesisError,
)
from .ledger import ResearchLedger

__all__ = [
    "CONTRADICTION", "CONTINGENT", "PROBLEMS", "TAUTOLOGY",
    "LeanChecker", "Problem", "TruthTableChecker", "classify", "run_benchmark",
    "STAGES", "MissingEvidenceError", "ResearchCycle", "ResearchError",
    "StageOrderError", "VerificationRequiredError",
    "REFUTED", "SUPPORTED", "Hypothesis", "HypothesisBook", "HypothesisError",
    "ResearchLedger",
]
