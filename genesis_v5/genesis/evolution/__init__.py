"""Genesis V6 Evolution layer.

Self-observation and self-proposal. The system reads its own recent behaviour
(decisions, failures, agent outcomes) and turns it into a small, ranked,
review-gated backlog of improvements. It never edits, deploys or acts on the
world — it observes and proposes, and a human decides.
"""
from __future__ import annotations

from .evolution import (
    EvolutionAgent,
    EvolutionConfig,
    EvolutionProposal,
    EvolutionReport,
    Improvement,
    LearningRecord,
    ProposalStore,
)
from .signals import (
    HealthSignal,
    ImprovementSignal,
    SignalCollector,
    WeaknessSignal,
)

__all__ = [
    "EvolutionAgent",
    "EvolutionConfig",
    "EvolutionProposal",
    "EvolutionReport",
    "Improvement",
    "ImprovementSignal",
    "HealthSignal",
    "LearningRecord",
    "ProposalStore",
    "SignalCollector",
    "WeaknessSignal",
]
