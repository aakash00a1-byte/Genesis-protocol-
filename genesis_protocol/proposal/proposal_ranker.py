"""Proposal Ranker - Genesis Protocol v1.8"""

from typing import List, Dict


class ProposalRanker:
    def __init__(self):
        self.weights = {"importance": 0.3, "confidence": 0.25, "impact": 0.25, "risk_penalty": 0.2}
    
    def rank(self, proposals: List[Dict]) -> List[Dict]:
        for p in proposals:
            p["rank_score"] = self._calculate_score(p)
        return sorted(proposals, key=lambda x: x["rank_score"], reverse=True)
    
    def _calculate_score(self, proposal: Dict) -> float:
        importance = proposal.get("importance", 0.5)
        confidence = proposal.get("confidence", 0.5)
        impact = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(proposal.get("estimated_impact", "medium"), 0.5)
        risk = {"safe": 1.0, "moderate": 0.5, "dangerous": 0.1}.get(proposal.get("risk_level", "moderate"), 0.5)
        
        score = (
            importance * self.weights["importance"] +
            confidence * self.weights["confidence"] +
            impact * self.weights["impact"] +
            risk * self.weights["risk_penalty"]
        )
        return round(score, 2)
    
    def get_top_proposals(self, proposals: List[Dict], n: int = 5) -> List[Dict]:
        return self.rank(proposals)[:n]


_ranker = None


def get_proposal_ranker() -> ProposalRanker:
    global _ranker
    if _ranker is None:
        _ranker = ProposalRanker()
    return _ranker
