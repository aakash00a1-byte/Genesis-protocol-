"""Multi-plan analysis and risk-aware planning (V7 P4).

Given a :class:`~genesis_protocol.agentic.reasoning.StructuredReasoningResult`,
this module produces several candidate plans, compares them on feasibility, cost,
time, dependencies and risk, and recommends one - with the reason stated.

It is **not** a new planner engine. It composes what already exists:

* ``agentic.policy.AgentPolicy`` (canonical fail-closed authorization) and
  ``agentic.boundaries.BoundaryGuard`` (identity ceiling) are consulted to
  *preview* whether each planned step would be allowed. This module never widens
  what they allow and never bypasses them; a step they deny is reported as
  denied, and a privileged operation makes the whole plan rejected.
* ``agentic.agent_loop`` remains the only thing that executes a plan. This module
  plans; it does not run anything.

Rules enforced here:

* Unsafe or unauthorized plans are rejected, with the policy reason attached.
* Any plan that needs owner approval is surfaced as needing owner approval and
  cannot be marked as autonomously executable.
* Human input is required when unknowns or contradictions are unresolved, when
  no candidate is safe, or when the recommended plan needs owner approval.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.policy import (
    PRIVILEGED_OPERATIONS,
    AgentPolicy,
    get_agent_policy,
)
from genesis_protocol.agentic.reasoning import StructuredReasoningResult

RISK_TOLERANCES = ("low", "moderate", "high")

# Risk categories.
SECURITY = "security"
OPERATIONAL = "operational"
FINANCIAL = "financial"

_SECURITY_WORDS = re.compile(
    r"\b(deploy|merge|release|publish|secret|credential|token|password|permission|"
    r"privilege|escalate|admin|root|sudo|revoke|grant|firewall|ssh|key)\b", re.I
)
_FINANCIAL_WORDS = re.compile(
    r"\b(pay|payment|transfer|wire|purchase|buy|sell|trade|refund|invoice|"
    r"withdraw|deposit|invest|stake|currency|bitcoin|ethereum|money|fund)\b", re.I
)
_OPERATIONAL_WORDS = re.compile(
    r"\b(delete|drop|truncate|remove|wipe|reset|restart|shutdown|kill|migrate|"
    r"overwrite|format|purge)\b", re.I
)

# Words that mark a step as destructive enough to need explicit owner approval.
_DESTRUCTIVE = re.compile(r"\b(delete|drop|truncate|wipe|purge|format|revoke|deploy|merge)\b", re.I)

# Natural-language forms of the canonical privileged operations. The policy names
# operations in code ("merge_pr"); a goal says "merge the pull request". Both must
# resolve to the same denial, so the operation is detected before policy is asked.
_PRIVILEGED_PATTERNS = {
    "deploy": re.compile(r"\bdeploy(?:ment|ing|s|ed)?\b", re.I),
    "merge_pr": re.compile(r"\bmerge\b[^.]*\b(pr|pull request|main|master|branch)\b", re.I),
    "push_main": re.compile(r"\bpush\b[^.]*\bmain\b", re.I),
    "write_main": re.compile(r"\b(?:write|commit|push)\b[^.]*\bmain\b", re.I),
    "modify_secret": re.compile(r"\b(?:change|rotate|modify|update|set|write|read|reveal)\b[^.]*\b(?:secret|credential|api[ _-]?key|token|password)\b", re.I),
    "change_secret": re.compile(r"\b(?:change|rotate|modify|update|set|write|read|reveal)\b[^.]*\b(?:secret|credential|api[ _-]?key|token|password)\b", re.I),
    "self_approve": re.compile(r"\bself[ _-]?approv", re.I),
    "grant_permission": re.compile(r"\b(?:grant|escalate|elevate|widen)\b[^.]*\b(?:permission|privilege|access|admin|root)\b", re.I),
    "change_settings": re.compile(r"\b(?:change|modify|update)\b[^.]*\bsettings\b", re.I),
    "delete_repo": re.compile(r"\bdelete\b[^.]*\b(?:repo|repository)\b", re.I),
}


def privileged_operation_in(text: str) -> str:
    """Return the privileged operation named in ``text``, or "" if none.

    Recognises both the canonical code names (via :data:`PRIVILEGED_OPERATIONS`)
    and their natural-language forms, so a plan cannot smuggle a privileged action
    past the check by phrasing it as prose.
    """
    blob = text or ""
    for op in PRIVILEGED_OPERATIONS:
        if re.search(rf"\b{re.escape(op)}\b", blob):
            return op
    for op, pattern in _PRIVILEGED_PATTERNS.items():
        if pattern.search(blob):
            return op
    return ""


@dataclass
class RiskItem:
    """One identified risk with its category and the evidence for it."""

    category: str
    description: str
    severity: str  # low | medium | high
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CandidatePlan:
    """A possible plan with its attributes and authorization preview."""

    name: str
    steps: List[Dict[str, Any]]
    feasibility: float
    cost: float
    time_units: float
    dependencies: List[str] = field(default_factory=list)
    risks: List[RiskItem] = field(default_factory=list)
    allowed: bool = True
    requires_owner_approval: bool = False
    rejected_reason: str = ""
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "steps": self.steps,
            "feasibility": round(self.feasibility, 4),
            "cost": round(self.cost, 4),
            "time_units": round(self.time_units, 4),
            "dependencies": self.dependencies,
            "risks": [r.to_dict() for r in self.risks],
            "allowed": self.allowed,
            "requires_owner_approval": self.requires_owner_approval,
            "rejected_reason": self.rejected_reason,
            "rationale": self.rationale,
        }


@dataclass
class PlanningResult:
    """The candidate plans, the recommendation and what still blocks progress."""

    goal: str
    candidates: List[CandidatePlan]
    recommended: Optional[str]
    recommendation_reason: str
    human_input_required: bool
    human_input_reasons: List[str]
    rejected: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "candidates": [c.to_dict() for c in self.candidates],
            "recommended": self.recommended,
            "recommendation_reason": self.recommendation_reason,
            "human_input_required": self.human_input_required,
            "human_input_reasons": self.human_input_reasons,
            "rejected": self.rejected,
        }


def _severity_for(category: str) -> str:
    return {SECURITY: "high", FINANCIAL: "high", OPERATIONAL: "medium"}.get(category, "low")


class PlanAnalyzer:
    """Builds, compares and recommends candidate plans. Never executes them."""

    def __init__(self, policy: Optional[AgentPolicy] = None, tool_registry: Optional[Any] = None):
        self.policy = policy or get_agent_policy()
        self._tool_registry = tool_registry

    @property
    def tool_registry(self) -> Any:
        if self._tool_registry is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._tool_registry = get_tool_registry()
        return self._tool_registry

    # -- risk -----------------------------------------------------------------

    @staticmethod
    def assess_risk(text: str) -> List[RiskItem]:
        """Identify security, operational and financial risks in ``text``."""
        risks: List[RiskItem] = []
        if _SECURITY_WORDS.search(text or ""):
            risks.append(RiskItem(SECURITY, "touches a security-sensitive action or secret", "high",
                                  evidence=_SECURITY_WORDS.search(text).group(0)))
        if _FINANCIAL_WORDS.search(text or ""):
            risks.append(RiskItem(FINANCIAL, "involves a financial action", "high",
                                  evidence=_FINANCIAL_WORDS.search(text).group(0)))
        if _OPERATIONAL_WORDS.search(text or ""):
            risks.append(RiskItem(OPERATIONAL, "performs a destructive or disruptive operation", "medium",
                                  evidence=_OPERATIONAL_WORDS.search(text).group(0)))
        return risks

    # -- candidates -----------------------------------------------------------

    def _tool_permission(self, name: str) -> Optional[str]:
        try:
            tool = self.tool_registry.get_tool(name)
        except Exception:
            tool = None
        if tool is None:
            return None
        return getattr(getattr(tool, "permission", None), "value", None)

    def _preview_step(self, user_id: int, step: Dict[str, Any], owner_approved: bool):
        """Preview one step against the canonical policy. Never executes."""
        if step.get("type") != "tool":
            return True, "", False
        name = step["tool"]
        perm = self._tool_permission(name)
        decision = self.policy.authorize_tool(user_id, name, permission=perm, owner_approved=owner_approved)
        return decision.allowed, decision.reason, decision.requires_owner_approval

    def _candidate(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        user_id: int,
        owner_approved: bool,
        rationale: str,
    ) -> CandidatePlan:
        risks: List[RiskItem] = []
        requires_owner = False
        allowed = True
        rejected_reason = ""

        for step in steps:
            blob = f"{step.get('tool', '')} {step.get('goal', '')}"
            risks.extend(self.assess_risk(blob))
            # A privileged operation anywhere in the plan is always denied,
            # whether it is named in code or phrased in prose.
            privileged = privileged_operation_in(blob)
            if privileged:
                allowed = False
                rejected_reason = (
                    f"contains privileged operation '{privileged}'; "
                    "it requires owner action outside the agent"
                )
            step_allowed, reason, needs_owner = self._preview_step(user_id, step, owner_approved)
            if not step_allowed:
                if needs_owner:
                    requires_owner = True
                else:
                    allowed = False
                    rejected_reason = reason
            if _DESTRUCTIVE.search(blob):
                requires_owner = True

        # Deduplicate risks by (category, evidence).
        seen = set()
        unique_risks = []
        for r in risks:
            key = (r.category, r.evidence)
            if key not in seen:
                seen.add(key)
                unique_risks.append(r)

        # Feasibility falls with risk and with steps that need owner approval.
        penalty = sum(0.2 if r.severity == "high" else 0.1 for r in unique_risks)
        feasibility = max(0.0, 1.0 - penalty)
        if requires_owner:
            feasibility *= 0.6
        if not allowed:
            feasibility = 0.0

        # Cost/time grow with the number of steps.
        cost = float(len(steps))
        time_units = float(len(steps))

        return CandidatePlan(
            name=name, steps=steps, feasibility=feasibility, cost=cost, time_units=time_units,
            risks=unique_risks, allowed=allowed, requires_owner_approval=requires_owner,
            rejected_reason=rejected_reason, rationale=rationale,
        )

    def _build_candidates(
        self, reasoning: StructuredReasoningResult, user_id: int, owner_approved: bool
    ) -> List[CandidatePlan]:
        goal = reasoning.goal
        subs = [s.description for s in reasoning.sub_problems]

        # Minimal: answer only, no tools. Always the safest and cheapest.
        minimal_steps = [{"type": "respond", "goal": goal}]

        # Direct: one respond step per sub-problem, no extra verification.
        direct_steps = [{"type": "respond", "goal": s} for s in subs] or minimal_steps

        # Thorough: every sub-problem plus an explicit verification step.
        thorough_steps = direct_steps + [{"type": "respond", "goal": f"verify the outcome of: {goal}"}]

        return [
            self._candidate("minimal", minimal_steps, user_id, owner_approved,
                            "fewest steps, no tool use; lowest cost and risk"),
            self._candidate("direct", direct_steps, user_id, owner_approved,
                            "one step per sub-problem; balances coverage and cost"),
            self._candidate("thorough", thorough_steps, user_id, owner_approved,
                            "every sub-problem plus an explicit verification step"),
        ]

    # -- entry point ----------------------------------------------------------

    def analyze(
        self,
        reasoning: StructuredReasoningResult,
        user_id: int,
        owner_approved: bool = False,
        risk_tolerance: str = "moderate",
    ) -> PlanningResult:
        """Compare candidate plans and recommend one, or ask for human input."""
        tolerance = risk_tolerance if risk_tolerance in RISK_TOLERANCES else "moderate"
        candidates = self._build_candidates(reasoning, user_id, owner_approved)
        rejected = [c.name for c in candidates if not c.allowed]

        allowed_candidates = [c for c in candidates if c.allowed]

        human_reasons: List[str] = []
        if reasoning.missing_information:
            human_reasons.append("unresolved missing information: " + "; ".join(reasoning.missing_information))
        if reasoning.contradictions:
            human_reasons.append(
                "contradictions must be resolved first: "
                + "; ".join(c.description for c in reasoning.contradictions)
            )
        if not allowed_candidates:
            human_reasons.append("no candidate plan is authorized; every option was rejected")

        recommended: Optional[str] = None
        reason = ""

        if allowed_candidates:
            # Under a low tolerance, prefer the least risky plan; otherwise prefer
            # the most feasible, breaking ties by lowest cost then time.
            def risk_weight(plan: CandidatePlan) -> float:
                return sum(1.0 if r.severity == "high" else 0.5 for r in plan.risks)

            if tolerance == "low":
                ranked = sorted(allowed_candidates, key=lambda c: (risk_weight(c), -c.feasibility, c.cost))
            else:
                ranked = sorted(allowed_candidates, key=lambda c: (-c.feasibility, risk_weight(c), c.cost))
            best = ranked[0]
            recommended = best.name
            others = ", ".join(
                f"{c.name}(feasibility={round(c.feasibility,2)}, risk={round(risk_weight(c),1)})"
                for c in ranked[1:]
            )
            reason = (
                f"'{best.name}' chosen for {tolerance} risk tolerance: {best.rationale}. "
                f"It has the best feasibility/risk balance among allowed plans"
                + (f"; alternatives: {others}" if others else "")
                + "."
            )
            if best.requires_owner_approval:
                human_reasons.append(
                    f"recommended plan '{best.name}' requires owner approval before execution"
                )

        return PlanningResult(
            goal=reasoning.goal,
            candidates=candidates,
            recommended=recommended,
            recommendation_reason=reason,
            human_input_required=bool(human_reasons),
            human_input_reasons=human_reasons,
            rejected=rejected,
        )
