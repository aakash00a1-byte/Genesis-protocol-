"""Improvement proposals (V7 P9).

A proposal is a *candidate* improvement: what to change, why, the evidence
behind it, and how it was verified. Proposals are the unit a human reviews; an
agent may create and verify them, but only an owner approves one for landing.

Risk is assessed with the canonical ``improvement.risk_engine.RiskEngine`` so P9
does not invent a second risk model, and every proposal can be projected into
the canonical ``proposal.ProposalManager`` shape for the existing review flow.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genesis_protocol.improvement.risk_engine import get_risk_engine

STATUS_PROPOSED = "proposed"
STATUS_EXPERIMENTING = "experimenting"
STATUS_VERIFIED = "verified"
STATUS_REJECTED = "rejected"
STATUS_READY = "ready"  # verified + owner-reviewable

VALID_STATUS = {
    STATUS_PROPOSED,
    STATUS_EXPERIMENTING,
    STATUS_VERIFIED,
    STATUS_REJECTED,
    STATUS_READY,
}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvolutionProposal:
    """A proposed, verifiable improvement to the system."""

    proposal_id: str
    title: str
    rationale: str
    change: Dict[str, str]  # repo-relative path -> proposed content (may be empty)
    created_at: str = field(default_factory=utcnow)
    status: str = STATUS_PROPOSED
    risk: Dict[str, Any] = field(default_factory=dict)
    evidence: List[str] = field(default_factory=list)
    experiment_id: Optional[str] = None
    regression_tests: Dict[str, str] = field(default_factory=dict)
    created_by: str = "self-evolution"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionProposal":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_canonical(self) -> Dict[str, Any]:
        """Project into the canonical ``proposal`` manager shape."""
        return {
            "title": self.title,
            "description": self.rationale,
            "category": "self_improvement",
            "evidence": list(self.evidence),
            "proposed_solution": self.rationale,
            "files_affected": sorted(self.change),
            "risk_level": self.risk.get("risk_level", "moderate"),
            "confidence": 1.0 - float(self.risk.get("risk_score", 0.5)),
        }


class ProposalStore:
    """In-memory proposal store with optional JSONL persistence."""

    def __init__(self, path: Optional[str] = None):
        self.path = path or os.environ.get("GENESIS_EVOLUTION_STORE")
        self._items: Dict[str, EvolutionProposal] = {}
        self._lock = threading.Lock()
        if self.path:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def add(self, proposal: EvolutionProposal) -> EvolutionProposal:
        with self._lock:
            self._items[proposal.proposal_id] = proposal
        self._persist(proposal)
        return proposal

    def create(
        self,
        title: str,
        rationale: str,
        change: Optional[Dict[str, str]] = None,
        evidence: Optional[List[str]] = None,
        proposal_id: Optional[str] = None,
    ) -> EvolutionProposal:
        change = change or {}
        risk = get_risk_engine().assess_risk({
            "proposed_solution": rationale,
            "files_affected": sorted(change),
        })
        proposal = EvolutionProposal(
            proposal_id=proposal_id or f"evo-{utcnow().replace(':', '').replace('-', '')}",
            title=title.strip(),
            rationale=rationale.strip(),
            change=dict(change),
            risk=risk,
            evidence=list(evidence or []),
        )
        return self.add(proposal)

    def get(self, proposal_id: str) -> Optional[EvolutionProposal]:
        return self._items.get(proposal_id)

    def list(self) -> List[EvolutionProposal]:
        return sorted(self._items.values(), key=lambda p: p.created_at, reverse=True)

    def update_status(self, proposal_id: str, status: str) -> EvolutionProposal:
        if status not in VALID_STATUS:
            raise ValueError(f"invalid proposal status '{status}'")
        with self._lock:
            proposal = self._items.get(proposal_id)
            if proposal is None:
                raise KeyError(f"unknown proposal '{proposal_id}'")
            proposal.status = status
        self._persist(proposal)
        return proposal

    def _persist(self, proposal: EvolutionProposal) -> None:
        if not self.path:
            return
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(proposal.to_dict(), sort_keys=True, default=str) + "\n")
