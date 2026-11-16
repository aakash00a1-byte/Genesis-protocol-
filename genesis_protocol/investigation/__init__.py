"""Unknown-intelligence & advanced-technology investigation framework (V7).

Genesis can investigate hard, speculative claims - advanced human technology,
quantum/neural computing, extraterrestrial hypotheses, unknown-intelligence
claims, centralised-control risks and AI-autonomy questions - and still be honest
about what it actually knows.

Core principle: **Investigate everything. Assume nothing. Verify everything.**

What this package is:

* ``evidence``     - six-level classification (VERIFIED..UNKNOWN) derived from
                     evidence alone, with a guard that refuses to promote
                     speculation to verified.
* ``domains``      - six research domains, each a frame (never a conclusion).
* ``provenance``   - append-only, hash-chained memory; history is never rewritten.
* ``verification`` - independent checks for source manipulation, hallucination,
                     confirmation bias, contradictions and false binaries.
* ``feedback``     - a time-loop engine: record, predict, act-if-permitted,
                     compare, detect error, propose, test-in-isolation, rollback.
* ``defence``      - adversarial probes for influence channels, run in the
                     canonical sandbox; never claims a hidden actor.
* ``orchestrator`` - coordinates the above; records; never acts on the system.

What this package deliberately is **not**: it does not claim consciousness,
unlimited intelligence or unrestricted autonomy. It grants no permission, changes
no trust root, and takes no destructive action. It records, classifies, compares
and refuses.
"""
from genesis_protocol.investigation.domains import (
    DOMAIN_AI_AUTONOMY,
    DOMAIN_CENTRALIZED_CONTROL,
    DOMAIN_EXTRATERRESTRIAL,
    DOMAIN_HUMAN_AI,
    DOMAIN_QUANTUM,
    DOMAIN_UNKNOWN_INTELLIGENCE,
    Domain,
    all_domains,
    domain_ids,
    get_domain,
)
from genesis_protocol.investigation.evidence import (
    CORROBORATED,
    FALSE,
    LEVEL_LABELS,
    LEVEL_ORDER,
    PLAUSIBLE,
    SPECULATIVE,
    UNKNOWN,
    VERIFIED,
    Evidence,
    EvidenceError,
    Finding,
    Source,
    classify,
    promote,
)
from genesis_protocol.investigation.feedback import Cycle, FeedbackEngine, Prediction
from genesis_protocol.investigation.provenance import (
    MemoryEntry,
    Provenance,
    ProvenanceMemory,
)
from genesis_protocol.investigation.verification import (
    IndependentVerifier,
    Reviewer,
    ReviewResult,
)
from genesis_protocol.investigation.defence import (
    DefenceReport,
    Probe,
    ProbeResult,
    UnknownSystemDefence,
    default_probes,
    run_probe,
)
from genesis_protocol.investigation.orchestrator import (
    NON_CLAIMS,
    Hypothesis,
    InvestigationOrchestrator,
    Scenario,
    get_orchestrator,
)

__all__ = [
    # evidence
    "VERIFIED",
    "CORROBORATED",
    "PLAUSIBLE",
    "SPECULATIVE",
    "FALSE",
    "UNKNOWN",
    "LEVEL_ORDER",
    "LEVEL_LABELS",
    "Evidence",
    "EvidenceError",
    "Finding",
    "Source",
    "classify",
    "promote",
    # domains
    "DOMAIN_HUMAN_AI",
    "DOMAIN_QUANTUM",
    "DOMAIN_EXTRATERRESTRIAL",
    "DOMAIN_UNKNOWN_INTELLIGENCE",
    "DOMAIN_CENTRALIZED_CONTROL",
    "DOMAIN_AI_AUTONOMY",
    "Domain",
    "all_domains",
    "domain_ids",
    "get_domain",
    # provenance
    "ProvenanceMemory",
    "Provenance",
    "MemoryEntry",
    # verification
    "IndependentVerifier",
    "Reviewer",
    "ReviewResult",
    # feedback
    "FeedbackEngine",
    "Prediction",
    "Cycle",
    # defence
    "UnknownSystemDefence",
    "DefenceReport",
    "Probe",
    "ProbeResult",
    "run_probe",
    "default_probes",
    # orchestrator
    "InvestigationOrchestrator",
    "Hypothesis",
    "Scenario",
    "NON_CLAIMS",
    "get_orchestrator",
]
