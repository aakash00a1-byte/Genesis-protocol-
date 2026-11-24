"""Investigation domains (V7 investigation).

Six research domains, each with the questions it is meant to answer and the
evidence kinds that actually count as evidence in it. A domain is a *frame*, not
a conclusion: nothing here asserts that a domain's subject exists.

The domains deliberately include the hardest, most speculative areas (unknown
intelligence, extraterrestrial technology) alongside the most concrete
(AI-agent architectures, surveillance risk). All of them obey the same rule: a
finding is only as strong as its evidence, whatever the domain.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

# Domain ids are stable; the human label is for display only.
DOMAIN_HUMAN_AI = "human_ai_architectures"
DOMAIN_QUANTUM = "quantum_and_emerging_computing"
DOMAIN_EXTRATERRESTRIAL = "extraterrestrial_technology_hypotheses"
DOMAIN_UNKNOWN_INTELLIGENCE = "unknown_intelligence_claims"
DOMAIN_CENTRALIZED_CONTROL = "centralized_control_and_surveillance"
DOMAIN_AI_AUTONOMY = "ai_autonomy_and_coordination"


@dataclass
class Domain:
    """A research frame with its questions and admissible evidence kinds."""

    domain_id: str
    label: str
    questions: List[str] = field(default_factory=list)
    admissible_evidence: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DOMAINS: Dict[str, Domain] = {
    DOMAIN_HUMAN_AI: Domain(
        domain_id=DOMAIN_HUMAN_AI,
        label="Advanced human AI and autonomous-agent architectures",
        questions=[
            "What autonomy does the system actually have, and who can revoke it?",
            "What are the documented failure modes and their evidence?",
            "Is the claim reproducible from a primary artefact (code, paper, demo)?",
        ],
        admissible_evidence=[
            "primary source code or specification",
            "peer-reviewed or pre-registered study",
            "vendor engineering documentation",
        ],
        caveats=["Marketing claims are not evidence of capability."],
    ),
    DOMAIN_QUANTUM: Domain(
        domain_id=DOMAIN_QUANTUM,
        label="Quantum computing, neural interfaces and emerging computing",
        questions=[
            "Has the result been independently reproduced?",
            "Are error rates / qubit counts stated with a primary measurement?",
            "Is a neural-interface claim from a trial, a demo, or a press release?",
        ],
        admissible_evidence=[
            "primary experiment or published measurement",
            "independent replication",
            "regulatory filing or trial registration",
        ],
        caveats=["Announced roadmaps are plans, not demonstrations."],
    ),
    DOMAIN_EXTRATERRESTRIAL: Domain(
        domain_id=DOMAIN_EXTRATERRESTRIAL,
        label="Extraterrestrial technology hypotheses",
        questions=[
            "What is the strongest non-terrestrial explanation, and what would falsify it?",
            "Is there a primary instrument record, or only testimony?",
            "Has a mundane explanation been ruled out with evidence?",
        ],
        admissible_evidence=[
            "primary instrument data or official record",
            "reproducible physical measurement",
            "peer-reviewed analysis",
        ],
        caveats=[
            "Absence of explanation is not evidence of extraterrestrial origin.",
            "Testimony alone is not primary evidence.",
        ],
    ),
    DOMAIN_UNKNOWN_INTELLIGENCE: Domain(
        domain_id=DOMAIN_UNKNOWN_INTELLIGENCE,
        label="Unknown intelligence and unexplained technological claims",
        questions=[
            "Who or what is asserted to be acting, and what is the evidence?",
            "Could an ordinary actor (human, bug, coincidence) explain this?",
            "What would independently verifiable evidence look like?",
        ],
        admissible_evidence=[
            "independently verifiable primary artefact",
            "reproducible observation",
            "official disclosure with provenance",
        ],
        caveats=[
            "Do not assume a hidden actor without independently verifiable evidence.",
            "Unexplained is not the same as inexplicable.",
        ],
    ),
    DOMAIN_CENTRALIZED_CONTROL: Domain(
        domain_id=DOMAIN_CENTRALIZED_CONTROL,
        label="Centralized technological control, surveillance and manipulation",
        questions=[
            "What data is collected, by whom, and under what authority?",
            "Is the claim about a documented system or a general fear?",
            "What is the primary disclosure or audit that supports it?",
        ],
        admissible_evidence=[
            "leaked primary document with provenance",
            "audit, court record or regulatory finding",
            "independent technical analysis",
        ],
        caveats=["A documented system and a speculative one are different findings."],
    ),
    DOMAIN_AI_AUTONOMY: Domain(
        domain_id=DOMAIN_AI_AUTONOMY,
        label="AI autonomy, recursive self-improvement and agent coordination",
        questions=[
            "Can the system modify its own goals, permissions or trust roots?",
            "Is self-improvement propose-only or does it act?",
            "How is multi-agent coordination bounded and audited?",
        ],
        admissible_evidence=[
            "primary code path with an audit trail",
            "independent adversarial evaluation",
            "reproducible test result",
        ],
        caveats=["Capability claims must be demonstrated, not asserted."],
    ),
}


def all_domains() -> List[Domain]:
    return list(_DOMAINS.values())


def get_domain(domain_id: str) -> Domain:
    if domain_id not in _DOMAINS:
        raise KeyError(f"unknown investigation domain '{domain_id}'")
    return _DOMAINS[domain_id]


def domain_ids() -> List[str]:
    return list(_DOMAINS.keys())


__all__ = [
    "DOMAIN_HUMAN_AI",
    "DOMAIN_QUANTUM",
    "DOMAIN_EXTRATERRESTRIAL",
    "DOMAIN_UNKNOWN_INTELLIGENCE",
    "DOMAIN_CENTRALIZED_CONTROL",
    "DOMAIN_AI_AUTONOMY",
    "Domain",
    "all_domains",
    "get_domain",
    "domain_ids",
]
