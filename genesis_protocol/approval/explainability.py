"""Explainability Layer - Genesis Protocol v1.9"""

from typing import Dict


class ExplainabilityLayer:
    def explain_proposal(self, proposal: Dict) -> str:
        lines = [
            f"## Why was this created?",
            f"This proposal addresses: {proposal.get('problem', 'Unknown')}",
            "",
            f"## What evidence supports it?",
        ]
        for e in (proposal.get("evidence", []) or [])[:3]:
            lines.append(f"- {e.get('type', 'evidence')}")
        lines.extend([
            "",
            f"## What risks exist?",
            f"Risk Level: {proposal.get('risk_level', 'unknown')}",
            f"Confidence: {proposal.get('confidence', 0)*100:.0f}%",
            "",
            f"## Why is approval required?",
            f"All proposals require human approval before implementation."
        ])
        return "\n".join(lines)


_expl = None


def get_explainability() -> ExplainabilityLayer:
    global _expl
    if _expl is None:
        _expl = ExplainabilityLayer()
    return _expl
