"""Approval Manager - Genesis Protocol v1.9"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    id: str
    proposal_id: str
    status: ApprovalStatus
    created_at: datetime
    updated_at: datetime
    decision_at: Optional[datetime] = None
    reason: str = ""
    user_id: str = "human"
    expires_in_days: int = 7
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "proposal_id": self.proposal_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "decision_at": self.decision_at.isoformat() if self.decision_at else None,
            "reason": self.reason,
            "user_id": self.user_id,
            "expires_in_days": self.expires_in_days
        }


class ApprovalManager:
    def __init__(self, storage_path: str = "./data/approvals"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._requests: Dict[str, ApprovalRequest] = {}
        self._counter = 0
        self._load_requests()
    
    def _load_requests(self):
        f = self.storage_path / "requests.json"
        if f.exists():
            try:
                data = json.load(open(f))
                for item in data:
                    item["status"] = ApprovalStatus(item["status"])
                    item["created_at"] = datetime.fromisoformat(item["created_at"])
                    item["updated_at"] = datetime.fromisoformat(item["updated_at"])
                    if item.get("decision_at"):
                        item["decision_at"] = datetime.fromisoformat(item["decision_at"])
                    self._requests[item["id"]] = ApprovalRequest(**item)
                    self._counter = max(self._counter, int(item["id"].split("-")[1]) if "-" in item["id"] else 0)
            except Exception:
                pass
    
    def _save_requests(self):
        f = self.storage_path / "requests.json"
        json.dump([r.to_dict() for r in self._requests.values()][-100:], open(f, "w"), indent=2)
    
    def create_request(self, proposal_id: str, expires_in_days: int = 7) -> ApprovalRequest:
        self._counter += 1
        rid = f"AR-{self._counter}"
        req = ApprovalRequest(
            id=rid,
            proposal_id=proposal_id,
            status=ApprovalStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_in_days=expires_in_days
        )
        self._requests[rid] = req
        self._save_requests()
        return req
    
    def approve(self, request_id: str, reason: str = "") -> ApprovalRequest:
        if request_id in self._requests:
            r = self._requests[request_id]
            r.status = ApprovalStatus.APPROVED
            r.decision_at = datetime.now()
            r.updated_at = datetime.now()
            r.reason = reason
            self._save_requests()
        return self._requests.get(request_id)
    
    def reject(self, request_id: str, reason: str = "") -> ApprovalRequest:
        if request_id in self._requests:
            r = self._requests[request_id]
            r.status = ApprovalStatus.REJECTED
            r.decision_at = datetime.now()
            r.updated_at = datetime.now()
            r.reason = reason
            self._save_requests()
        return self._requests.get(request_id)
    
    def defer(self, request_id: str, reason: str = "") -> ApprovalRequest:
        if request_id in self._requests:
            r = self._requests[request_id]
            r.updated_at = datetime.now()
            r.reason = reason
            self._save_requests()
        return self._requests.get(request_id)
    
    def get_pending(self) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == ApprovalStatus.PENDING]
    
    def get_by_status(self, status: ApprovalStatus) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.status == status]
    
    def get_history(self) -> Dict:
        return {
            "pending": len(self.get_by_status(ApprovalStatus.PENDING)),
            "approved": len(self.get_by_status(ApprovalStatus.APPROVED)),
            "rejected": len(self.get_by_status(ApprovalStatus.REJECTED)),
            "expired": len(self.get_by_status(ApprovalStatus.EXPIRED))
        }


_manager = None


def get_approval_manager() -> ApprovalManager:
    global _manager
    if _manager is None:
        _manager = ApprovalManager()
    return _manager
