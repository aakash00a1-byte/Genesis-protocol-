"""Patch Proposal - Genesis Protocol v1.7
Structured proposals for improvements."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class RiskLevel(Enum):
    """Risk levels for proposals."""
    SAFE = "safe"
    MODERATE = "moderate"
    DANGEROUS = "dangerous"


class ProposalStatus(Enum):
    """Status of a proposal."""
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"


@dataclass
class PatchProposal:
    """A structured improvement proposal."""
    id: str
    problem: str
    evidence: List[str]
    proposed_solution: str
    risk_level: RiskLevel
    confidence: float  # 0.0 - 1.0
    status: ProposalStatus
    created_at: datetime
    related_weakness: Optional[str] = None
    estimated_impact: str = ""
    test_plan: str = ""
    created_by: str = "self"  # "self" or "human"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "problem": self.problem,
            "evidence": self.evidence,
            "proposed_solution": self.proposed_solution,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "related_weakness": self.related_weakness,
            "estimated_impact": self.estimated_impact,
            "test_plan": self.test_plan,
            "created_by": self.created_by
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PatchProposal':
        data['risk_level'] = RiskLevel(data['risk_level'])
        data['status'] = ProposalStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)


class ProposalGenerator:
    """Generates improvement proposals from weaknesses."""
    
    def __init__(self, storage_path: str = "./data/proposals"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._proposals: Dict[str, PatchProposal] = {}
        self._proposal_counter = 0
        self._load_proposals()
    
    def _load_proposals(self):
        """Load proposals from disk."""
        prop_file = self.storage_path / "proposals.json"
        if prop_file.exists():
            try:
                with open(prop_file, 'r') as f:
                    data = json.load(f)
                for item in data:
                    prop = PatchProposal.from_dict(item)
                    self._proposals[prop.id] = prop
                    # Update counter
                    num = int(prop.id.split('_')[1]) if '_' in prop.id else 0
                    self._proposal_counter = max(self._proposal_counter, num)
            except Exception:
                pass
    
    def _save_proposals(self):
        """Save proposals to disk."""
        prop_file = self.storage_path / "proposals.json"
        data = [p.to_dict() for p in self._proposals.values()]
        try:
            with open(prop_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def generate_proposal(
        self,
        problem: str,
        evidence: List[str],
        proposed_solution: str,
        risk_level: RiskLevel,
        confidence: float,
        related_weakness: Optional[str] = None
    ) -> PatchProposal:
        """Generate a new proposal."""
        self._proposal_counter += 1
        prop_id = f"prop_{self._proposal_counter}"
        
        proposal = PatchProposal(
            id=prop_id,
            problem=problem,
            evidence=evidence,
            proposed_solution=proposed_solution,
            risk_level=risk_level,
            confidence=confidence,
            status=ProposalStatus.DRAFT,
            created_at=datetime.now(),
            related_weakness=related_weakness
        )
        
        self._proposals[prop_id] = proposal
        self._save_proposals()
        
        return proposal
    
    def propose(self, proposal_id: str):
        """Mark proposal as proposed (ready for review)."""
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = ProposalStatus.PROPOSED
            self._save_proposals()
    
    def approve(self, proposal_id: str):
        """Mark proposal as approved (requires human approval in real system)."""
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = ProposalStatus.APPROVED
            self._save_proposals()
    
    def reject(self, proposal_id: str):
        """Mark proposal as rejected."""
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = ProposalStatus.REJECTED
            self._save_proposals()
    
    def implement(self, proposal_id: str):
        """Mark proposal as implemented."""
        if proposal_id in self._proposals:
            self._proposals[proposal_id].status = ProposalStatus.IMPLEMENTED
            self._save_proposals()
    
    def get_proposal(self, proposal_id: str) -> Optional[PatchProposal]:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)
    
    def get_all_proposals(self) -> List[PatchProposal]:
        """Get all proposals."""
        return list(self._proposals.values())
    
    def get_proposed_proposals(self) -> List[PatchProposal]:
        """Get proposals ready for review."""
        return [p for p in self._proposals.values() if p.status == ProposalStatus.PROPOSED]
    
    def get_by_risk(self, risk_level: RiskLevel) -> List[PatchProposal]:
        """Get proposals by risk level."""
        return [p for p in self._proposals.values() if p.risk_level == risk_level]
    
    def generate_from_weakness(self, weakness: Dict) -> PatchProposal:
        """Generate a proposal from a weakness."""
        weak_type = weakness.get("type", "")
        severity = weakness.get("severity", 0.5)
        
        # Generate solution based on weakness type
        solutions = {
            "memory_recall": {
                "solution": "Improve summarization to store more context. "
                           "Consider increasing reflection frequency.",
                "risk": RiskLevel.MODERATE,
                "confidence": 0.7
            },
            "coding_accuracy": {
                "solution": "Add more code examples to training. "
                           "Implement syntax validation.",
                "risk": RiskLevel.SAFE,
                "confidence": 0.8
            },
            "response_latency": {
                "solution": "Cache frequent responses. "
                           "Optimize provider selection.",
                "risk": RiskLevel.MODERATE,
                "confidence": 0.75
            },
            "task_completion": {
                "solution": "Add task tracking reminders. "
                           "Implement better task queue management.",
                "risk": RiskLevel.SAFE,
                "confidence": 0.85
            },
        }
        
        default = {
            "solution": "Investigate root cause and propose targeted fix.",
            "risk": RiskLevel.DANGEROUS,
            "confidence": 0.5
        }
        
        config = solutions.get(weak_type, default)
        
        return self.generate_proposal(
            problem=weakness.get("description", "Unknown issue"),
            evidence=weakness.get("evidence", []),
            proposed_solution=config["solution"],
            risk_level=config["risk"],
            confidence=config["confidence"] * (1 - severity * 0.2),
            related_weakness=weak_type
        )


# Global singleton
_proposal_generator: Optional[ProposalGenerator] = None


def get_proposal_generator() -> ProposalGenerator:
    """Get global proposal generator."""
    global _proposal_generator
    if _proposal_generator is None:
        _proposal_generator = ProposalGenerator()
    return _proposal_generator
