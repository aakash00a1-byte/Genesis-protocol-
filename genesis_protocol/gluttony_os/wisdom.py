"""Wisdom Layer - GLUTTONY Presence Layer

Distinguishes facts, assumptions, beliefs, and unknowns."""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class WisdomLayer:
    """Manages epistemic states: facts, assumptions, beliefs, unknowns."""
    
    def __init__(self, storage_path: str = "data/wisdom.json"):
        self.storage_path = storage_path
        self._ensure_storage()
        self.facts: List[Dict] = []
        self.assumptions: List[Dict] = []
        self.beliefs: List[Dict] = []
        self.unknowns: List[Dict] = []
        self._load()
    
    def _ensure_storage(self):
        """Ensure storage directory exists."""
        Path(self.storage_path).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """Load wisdom state from disk."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    self.facts = data.get('facts', [])
                    self.assumptions = data.get('assumptions', [])
                    self.beliefs = data.get('beliefs', [])
                    self.unknowns = data.get('unknowns', [])
            except Exception:
                pass
    
    def _save(self):
        """Save wisdom state to disk."""
        data = {
            'facts': self.facts,
            'assumptions': self.assumptions,
            'beliefs': self.beliefs,
            'unknowns': self.unknowns,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_fact(self, statement: str, source: str = "observation",
                 confidence: float = 1.0) -> str:
        """Add a verified fact."""
        fact = {
            'id': f"fact_{len(self.facts)}_{int(datetime.now().timestamp())}",
            'statement': statement,
            'source': source,
            'confidence': confidence,
            'verified_at': datetime.now().isoformat()
        }
        self.facts.append(fact)
        self._save()
        return fact['id']
    
    def add_assumption(self, statement: str, reason: str = "",
                      confidence: float = 0.5) -> str:
        """Add an assumption (untested belief)."""
        assumption = {
            'id': f"assm_{len(self.assumptions)}_{int(datetime.now().timestamp())}",
            'statement': statement,
            'reason': reason,
            'confidence': confidence,
            'created_at': datetime.now().isoformat()
        }
        self.assumptions.append(assumption)
        self._save()
        return assumption['id']
    
    def add_belief(self, statement: str, evidence: str = "",
                  confidence: float = 0.7) -> str:
        """Add a belief (held with some confidence)."""
        belief = {
            'id': f"bel_{len(self.beliefs)}_{int(datetime.now().timestamp())}",
            'statement': statement,
            'evidence': evidence,
            'confidence': confidence,
            'created_at': datetime.now().isoformat()
        }
        self.beliefs.append(belief)
        self._save()
        return belief['id']
    
    def add_unknown(self, question: str, context: str = "") -> str:
        """Add an unknown/question to investigate."""
        unknown = {
            'id': f"unk_{len(self.unknowns)}_{int(datetime.now().timestamp())}",
            'question': question,
            'context': context,
            'asked_at': datetime.now().isoformat(),
            'investigated': False
        }
        self.unknowns.append(unknown)
        self._save()
        return unknown['id']
    
    def promote_to_fact(self, item_id: str, source: str = "verified"):
        """Promote an assumption or belief to fact."""
        # Check assumptions
        for a in self.assumptions:
            if a['id'] == item_id:
                self.add_fact(a['statement'], source, 1.0)
                self.assumptions.remove(a)
                self._save()
                return True
        
        # Check beliefs
        for b in self.beliefs:
            if b['id'] == item_id:
                self.add_fact(b['statement'], source, b.get('confidence', 1.0))
                self.beliefs.remove(b)
                self._save()
                return True
        
        return False
    
    def mark_investigated(self, item_id: str):
        """Mark an unknown as investigated."""
        for u in self.unknowns:
            if u['id'] == item_id:
                u['investigated'] = True
                self._save()
                return True
        return False
    
    def get_wisdom_summary(self) -> Dict:
        """Get wisdom layer summary."""
        return {
            'facts_count': len(self.facts),
            'assumptions_count': len(self.assumptions),
            'beliefs_count': len(self.beliefs),
            'unknowns_count': len(self.unknowns),
            'unknowns_pending': len([u for u in self.unknowns if not u.get('investigated', False)])
        }
    
    def get_all(self) -> Dict:
        """Get all wisdom categories."""
        return {
            'facts': self.facts,
            'assumptions': self.assumptions,
            'beliefs': self.beliefs,
            'unknowns': [u for u in self.unknowns if not u.get('investigated', False)]
        }
    
    def get_full_state(self) -> Dict:
        """Get complete wisdom state for continuity."""
        return {
            'facts': self.facts,
            'assumptions': self.assumptions,
            'beliefs': self.beliefs,
            'unknowns': self.unknowns,
            'stats': self.get_wisdom_summary()
        }
    
    def restore(self, state: Dict):
        """Restore wisdom state from continuity data."""
        self.facts = state.get('facts', [])
        self.assumptions = state.get('assumptions', [])
        self.beliefs = state.get('beliefs', [])
        self.unknowns = state.get('unknowns', [])
        self._save()


_wisdom_layer: Optional[WisdomLayer] = None


def get_wisdom_layer() -> WisdomLayer:
    """Get wisdom layer singleton."""
    global _wisdom_layer
    if _wisdom_layer is None:
        _wisdom_layer = WisdomLayer()
    return _wisdom_layer
