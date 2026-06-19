"""Proposal Manager - Genesis Protocol v1.8
Manages proposal lifecycle from draft to implemented."""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class ProposalStatus(Enum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    IMPLEMENTED = "implemented"
    FAILED = "failed"


class ProposalCategory(Enum):
    PERFORMANCE = "performance"
    MEMORY = "memory"
    TOOL = "tool"
    PROVIDER = "provider"
    BUG = "bug"
    CAPABILITY = "capability"


@dataclass
class Proposal:
    id: str
    title: str
    problem: str
    solution: str
    category: ProposalCategory
    status: ProposalStatus
    risk_level: str
    confidence: float
    evidence: List[Dict]
    affected_modules: List[str]
    created_at: datetime
    updated_at: datetime
    created_by: str = "self"
    commentary: str = ""
    estimated_benefit: str = ""
    implementation_plan: str = ""
    test_plan: str = ""
    rejection_reason: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "problem": self.problem,
            "solution": self.solution,
            "category": self.category.value,
            "status": self.status.value,
            "risk_level": self.risk_level,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "affected_modules": self.affected_modules,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "commentary": self.commentary,
            "estimated_benefit": self.estimated_benefit,
            "implementation_plan": self.implementation_plan,
            "test_plan": self.test_plan,
            "rejection_reason": self.rejection_reason
        }


class ProposalManager:
    def __init__(self, storage_path: str = "./data/proposals"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._proposals: Dict[str, Proposal] = {}
        self._counter = 0
        self._load_proposals()
    
    def _load_proposals(self):
        f = self.storage_path / "proposals.json"
        if f.exists():
            try:
                data = json.load(open(f))
                for item in data:
                    item["category"] = ProposalCategory(item["category"])
                    item["status"] = ProposalStatus(item["status"])
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                    item["updated_at"] = datetime.fromisoformat(item["updated_at"])
                    p = Proposal(**item)
                    self._proposals[p.id] = p
                    self._counter = max(self._counter, int(p.id.split("-")[1]) if "-" in p.id else 0)
            except:
                pass
    
    def _save_proposals(self):
        f = self.storage_path / "proposals.json"
        data = [p.to_dict() for p in self._proposals.values()]
        json.dump(data[-100:], open(f, "w"), indent=2)
    
    def create_proposal(
        self,
        title: str,
        problem: str,
        solution: str,
        category: ProposalCategory,
        risk_level: str,
        confidence: float,
        evidence: List[Dict] = None,
        affected_modules: List[str] = None,
        commentary: str = "",
        estimated_benefit: str = ""
    ) -> Proposal:
        self._counter += 1
        pid = f"P-{self._counter}"
        
        proposal = Proposal(
            id=pid,
            title=title,
            problem=problem,
            solution=solution,
            category=category,
            status=ProposalStatus.DRAFT,
            risk_level=risk_level,
            confidence=confidence,
            evidence=evidence or [],
            affected_modules=affected_modules or [],
            created_at=datetime.now(),
            updated_at=datetime.now(),
            commentary=commentary,
            estimated_benefit=estimated_benefit
        )
        
        self._proposals[pid] = proposal
        self._save_proposals()
        return proposal
    
    def submit_for_review(self, proposal_id: str) -> Proposal:
        if proposal_id in self._proposals:
            p = self._proposals[proposal_id]
            p.status = ProposalStatus.REVIEW
            p.updated_at = datetime.now()
            self._save_proposals()
        return self._proposals.get(proposal_id)
    
    def approve(self, proposal_id: str) -> Proposal:
        if proposal_id in self._proposals:
            p = self._proposals[proposal_id]
            p.status = ProposalStatus.APPROVED
            p.updated_at = datetime.now()
            self._save_proposals()
        return self._proposals.get(proposal_id)
    
    def reject(self, proposal_id: str, reason: str = "") -> Proposal:
        if proposal_id in self._proposals:
            p = self._proposals[proposal_id]
            p.status = ProposalStatus.REJECTED
            p.rejection_reason = reason
            p.updated_at = datetime.now()
            self._save_proposals()
        return self._proposals.get(proposal_id)
    
    def mark_implemented(self, proposal_id: str) -> Proposal:
        if proposal_id in self._proposals:
            p = self._proposals[proposal_id]
            p.status = ProposalStatus.IMPLEMENTED
            p.updated_at = datetime.now()
            self._save_proposals()
        return self._proposals.get(proposal_id)
    
    def mark_failed(self, proposal_id: str) -> Proposal:
        if proposal_id in self._proposals:
            p = self._proposals[proposal_id]
            p.status = ProposalStatus.FAILED
            p.updated_at = datetime.now()
            self._save_proposals()
        return self._proposals.get(proposal_id)
    
    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        return self._proposals.get(proposal_id)
    
    def get_all_proposals(self) -> List[Proposal]:
        return list(self._proposals.values())
    
    def get_by_status(self, status: ProposalStatus) -> List[Proposal]:
        return [p for p in self._proposals.values() if p.status == status]
    
    def get_by_category(self, category: ProposalCategory) -> List[Proposal]:
        return [p for p in self._proposals.values() if p.category == category]
    
    def get_history(self) -> Dict[str, int]:
        return {
            "total": len(self._proposals),
            "draft": len(self.get_by_status(ProposalStatus.DRAFT)),
            "review": len(self.get_by_status(ProposalStatus.REVIEW)),
            "approved": len(self.get_by_status(ProposalStatus.APPROVED)),
            "rejected": len(self.get_by_status(ProposalStatus.REJECTED)),
            "implemented": len(self.get_by_status(ProposalStatus.IMPLEMENTED))
        }


_manager = None


def get_proposal_manager() -> ProposalManager:
    global _manager
    if _manager is None:
        _manager = ProposalManager()
    return _manager
