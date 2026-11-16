"""Verified self-evolution (V7 P9).

Genesis may propose improvements to itself, but it may not land them. P9 makes
that loop *verifiable*:

* ``experiment``   - try a change in an isolated scratch tree (never the repo);
* ``proposals``    - record it with canonical risk assessment;
* ``regression``   - generate a test and require it to be red-before / green-after;
* ``adversarial``  - attack the change and require no regression;
* ``reversible``   - express the change so it can be applied and rolled back
                     with byte fidelity;
* ``engine``       - the loop and the gate that marks a proposal ``ready`` for
                     owner review, or rejects it.

Rules this package holds to:

* **Propose-only.** The engine never merges, deploys, or approves itself; a
  proposal is only ever ``ready`` *for a human*.
* **Evidence or nothing.** A proposal becomes ``ready`` only when its generated
  test discriminates and its adversarial evaluation is clean.
* **Isolated by construction.** Experiments, generated tests and probes run in
  the canonical sandbox against scratch trees; the repository is never written.
* **Reversible.** Any change carries a full backup and an atomic apply/rollback.
* **Auditable.** Every step is recorded in the canonical ``SecurityEventLog``
  under source ``evolution``.
"""
from genesis_protocol.evolution.adversarial import (
    AdversarialReport,
    Probe,
    ProbeResult,
    default_probes,
    evaluate,
    static_flags,
)
from genesis_protocol.evolution.engine import EvolutionEngine
from genesis_protocol.evolution.experiment import Experiment, ExperimentResult
from genesis_protocol.evolution.proposals import (
    STATUS_EXPERIMENTING,
    STATUS_PROPOSED,
    STATUS_READY,
    STATUS_REJECTED,
    STATUS_VERIFIED,
    EvolutionProposal,
    ProposalStore,
)
from genesis_protocol.evolution.regression import (
    RESULT_BROKEN,
    RESULT_NOT_DISCRIMINATING,
    RESULT_RED_GREEN,
    RegressionTest,
    generate_test_module,
    verify_red_green,
)
from genesis_protocol.evolution.reversible import (
    ChangeRefused,
    ReversibleChange,
    snapshot,
)

__all__ = [
    "EvolutionEngine",
    "Experiment",
    "ExperimentResult",
    "EvolutionProposal",
    "ProposalStore",
    "RegressionTest",
    "generate_test_module",
    "verify_red_green",
    "RESULT_RED_GREEN",
    "RESULT_NOT_DISCRIMINATING",
    "RESULT_BROKEN",
    "AdversarialReport",
    "Probe",
    "ProbeResult",
    "evaluate",
    "static_flags",
    "default_probes",
    "ReversibleChange",
    "ChangeRefused",
    "snapshot",
    "STATUS_PROPOSED",
    "STATUS_EXPERIMENTING",
    "STATUS_VERIFIED",
    "STATUS_REJECTED",
    "STATUS_READY",
]
