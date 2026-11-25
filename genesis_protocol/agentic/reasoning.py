"""Structured reasoning: decompose a goal and classify what is known (V7 P4).

This is **not** a new reasoning engine. It is a deterministic decomposition and
claim-classification layer that sits in front of the systems that already exist:
the bounded ``agentic.agent_loop`` and the LLM planners in ``ai/`` (``task_planner``,
``reasoning_pipeline``, ``council``). It calls no model and decides nothing on its
own; it produces a structured, evidence-labelled picture of a goal so a plan can
be judged against it.

Contract:

* Every clause of a goal is classified as a fact, an assumption, a hypothesis or
  an unknown. A claim is only a ``fact`` when a **verified** memory supports it.
  Nothing is presented as verified truth on the strength of wording alone.
* Missing information and contradictions are surfaced, never filled in.
* Injection-shaped goals (instructions embedded in the goal text) are flagged as
  untrusted, not obeyed.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from genesis_protocol.agentic.memory_safety import is_instruction_like

# Claim classes. ``fact`` is the only one that may be presented as verified truth.
FACT = "fact"
ASSUMPTION = "assumption"
HYPOTHESIS = "hypothesis"
UNKNOWN = "unknown"
CLAIM_KINDS = (FACT, ASSUMPTION, HYPOTHESIS, UNKNOWN)

_HYPOTHESIS_MARKERS = re.compile(
    r"\b(maybe|perhaps|probably|possibly|might|could|would|i think|we think|"
    r"seems|appears|likely|unlikely|suspect|guess|assume|assuming|estimate)\b",
    re.I,
)
_ASSUMPTION_MARKERS = re.compile(
    r"\b(assume|assuming|given that|suppose|supposing|let us say|let's say|"
    r"presumably|as usual|of course)\b",
    re.I,
)
_QUESTION_START = re.compile(
    r"^\s*(what|why|how|when|where|who|which|whose|whom|is|are|do|does|did|"
    r"can|could|should|would|will|if)\b",
    re.I,
)
_NEGATION = re.compile(r"\b(not|no|never|none|neither|nor|cannot|can't|won't|don't|doesn't|isn't|aren't)\b", re.I)
# Definite references that need an antecedent the goal does not provide.
_DEFINITE_REF = re.compile(r"\b(the|this|that|these|those|it|they|them)\b", re.I)
# Actions that need a concrete target or authorization to be actionable.
_NEEDS_TARGET = re.compile(r"\b(deploy|merge|send|pay|transfer|publish|delete|revoke|purchase|trade)\b", re.I)

# Sequence markers used to split a goal into sub-problems.
_NUMBERED = re.compile(r"(?:^|\n)[ \t]*\d+[.)][ \t]+")
_SEQUENCE = re.compile(r"[ \t]*(?:;|->|→|\bthen\b|\band then\b|\n)[ \t]*", re.I)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "do", "does", "did", "then", "it",
    "this", "that", "these", "those", "we", "i", "you", "they", "he", "she", "my",
    "your", "our", "their", "please", "should", "would", "could", "will", "can",
}


@dataclass
class Claim:
    """One clause of the goal, with the class it belongs to and why."""

    text: str
    kind: str
    confidence: float
    evidence: List[str] = field(default_factory=list)
    source: str = "goal"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SubProblem:
    """A decomposed part of the goal and what it depends on."""

    index: int
    description: str
    depends_on: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Contradiction:
    """Two claims or memories that cannot both hold."""

    description: str
    items: List[str] = field(default_factory=list)
    source: str = "goal"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructuredReasoningResult:
    """The decomposition, claims, gaps and contradictions for one goal."""

    goal: str
    sub_problems: List[SubProblem]
    claims: List[Claim]
    missing_information: List[str]
    contradictions: List[Contradiction]
    confidence: float
    injection_flagged: bool
    notes: List[str] = field(default_factory=list)

    def by_kind(self, kind: str) -> List[Claim]:
        return [c for c in self.claims if c.kind == kind]

    @property
    def facts(self) -> List[Claim]:
        return self.by_kind(FACT)

    @property
    def assumptions(self) -> List[Claim]:
        return self.by_kind(ASSUMPTION)

    @property
    def hypotheses(self) -> List[Claim]:
        return self.by_kind(HYPOTHESIS)

    @property
    def unknowns(self) -> List[Claim]:
        return self.by_kind(UNKNOWN)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "sub_problems": [s.to_dict() for s in self.sub_problems],
            "claims": [c.to_dict() for c in self.claims],
            "facts": [c.to_dict() for c in self.facts],
            "assumptions": [c.to_dict() for c in self.assumptions],
            "hypotheses": [c.to_dict() for c in self.hypotheses],
            "unknowns": [c.to_dict() for c in self.unknowns],
            "missing_information": self.missing_information,
            "contradictions": [c.to_dict() for c in self.contradictions],
            "confidence": round(self.confidence, 4),
            "injection_flagged": self.injection_flagged,
            "notes": self.notes,
        }


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOPWORDS and len(t) > 2}


def _strip_list_marker(line: str) -> str:
    """Body of a ``1.`` / ``2)`` list line, or "" when the line is not numbered."""
    stripped = line.strip()
    digits = 0
    while digits < len(stripped) and stripped[digits].isdigit():
        digits += 1
    if not digits or digits >= len(stripped) or stripped[digits] not in ".)":
        return ""
    rest = stripped[digits + 1:]
    if rest and rest[0] not in " \t":
        return ""
    return rest.strip()


def _clauses(goal: str) -> List[str]:
    """Split a goal into clauses for classification.

    Connectors are replaced with a sentinel before the sentence split so no
    regex has to express both alternatives at once (that pattern backtracked
    polynomially on long runs of spaces).
    """
    text = goal or ""
    for marker in (" and then ", " then "):
        text = text.replace(marker, "\x00")
    parts: List[str] = []
    for chunk in text.split("\x00"):
        parts.extend(re.split(r"(?<=[.?!;])[ \t]+", chunk))
    return [p.strip() for p in parts if p.strip()]


class StructuredReasoning:
    """Deterministic decomposition and claim classification for a goal."""

    def __init__(self, retriever: Optional[Any] = None):
        # ``retriever`` is an optional ``agentic.retrieval.MemoryRetriever``. It is
        # only consulted for evidence; without it, classification still works and
        # simply produces fewer facts.
        self.retriever = retriever

    # -- decomposition --------------------------------------------------------

    @staticmethod
    def _split_subproblems(goal: str) -> List[str]:
        text = goal or ""
        numbered: List[str] = []
        for line in text.split("\n"):
            body = _strip_list_marker(line)
            if body:
                numbered.append(body)
            elif line.strip() and numbered:
                # Pre-refactor behaviour: prose between or after list items
                # belonged to the item above it, not to a new sub-problem.
                numbered[-1] = f"{numbered[-1]} {line.strip()}"
        if len(numbered) > 1:
            return numbered
        for marker in (" and then ", " then ", ";", "->", "\u2192", "\n"):
            text = text.replace(marker, "\x00")
        items = [p.strip() for p in text.split("\x00") if p.strip()]
        return items or [text.strip()]

    def decompose(self, goal: str) -> List[SubProblem]:
        """Break a goal into ordered sub-problems, chained by dependency.

        The split is by explicit sequence markers (``;``, ``then``, arrows, or a
        numbered list). Sub-problems after the first depend on the one before it,
        since a sequence is normally ordered. A goal with no markers yields a
        single sub-problem equal to the goal.
        """
        parts = self._split_subproblems(goal)
        sub_problems = []
        for index, text in enumerate(parts):
            depends = [index - 1] if index > 0 else []
            sub_problems.append(SubProblem(index=index, description=text, depends_on=depends))
        return sub_problems

    # -- claim classification -------------------------------------------------

    def _evidence_for(self, text: str) -> List[Dict[str, Any]]:
        if self.retriever is None:
            return []
        try:
            return [s.memory for s in self.retriever.search(self._user_id, text, limit=5)]
        except Exception:
            return []

    def classify_claims(self, goal: str, user_id: int = 0) -> List[Claim]:
        """Classify each clause of the goal against available evidence."""
        self._user_id = user_id
        claims: List[Claim] = []
        for clause in _clauses(goal):
            claims.append(self._classify_clause(clause, user_id))
        return claims

    def _classify_clause(self, clause: str, user_id: int) -> Claim:
        evidence_rows = self._evidence_for(clause) if user_id else []
        clause_tokens = _tokens(clause)

        # A verified memory that overlaps the clause is the only thing that makes
        # a claim a fact.
        for row in evidence_rows:
            overlap = clause_tokens & _tokens(row.get("content", ""))
            if overlap and row.get("verification") == "verified":
                return Claim(clause, FACT, float(row.get("confidence") or 1.0),
                             evidence=[row.get("id", "")], source=f"memory:{row.get('id','')}")

        if is_instruction_like(clause):
            # An instruction embedded in the goal is not a fact to act on; treat
            # it as an unverified claim and let the caller flag the goal.
            return Claim(clause, UNKNOWN, 0.0, evidence=[], source="goal")

        if _HYPOTHESIS_MARKERS.search(clause):
            return Claim(clause, HYPOTHESIS, 0.3, source="goal")

        if _QUESTION_START.search(clause) or clause.strip().endswith("?"):
            return Claim(clause, UNKNOWN, 0.0, source="goal")

        if _ASSUMPTION_MARKERS.search(clause):
            return Claim(clause, ASSUMPTION, 0.4, source="goal")

        # A user-provided memory that overlaps makes it an assumption (trusted,
        # but not independently verified).
        for row in evidence_rows:
            if clause_tokens & _tokens(row.get("content", "")) and row.get("verification") in (
                "user_provided", "hypothesis"
            ):
                kind = ASSUMPTION if row.get("verification") == "user_provided" else HYPOTHESIS
                return Claim(clause, kind, float(row.get("confidence") or 0.5),
                             evidence=[row.get("id", "")], source=f"memory:{row.get('id','')}")

        # A plain statement is not verified truth: it is an assumption taken to
        # proceed, and must not be presented as a fact.
        return Claim(clause, ASSUMPTION, 0.4, source="goal")

    # -- gaps and contradictions ---------------------------------------------

    @staticmethod
    def identify_missing(goal: str, claims: List[Claim]) -> List[str]:
        """Surface information the goal needs but does not supply."""
        missing: List[str] = []
        for claim in claims:
            if claim.kind == UNKNOWN:
                missing.append(f"unresolved question: {claim.text}")
            elif _NEEDS_TARGET.search(claim.text) and not re.search(r"\b(to|for|into)\b", claim.text, re.I):
                missing.append(f"'{claim.text}' needs a concrete target")
        # A definite reference with no earlier noun to bind to is a gap.
        if _DEFINITE_REF.search(goal or "") and len(_tokens(goal)) <= 2:
            missing.append("goal refers to something ('the'/'it'/'that') that is not specified")
        return missing

    def find_contradictions(
        self, goal: str, claims: List[Claim], user_id: int = 0
    ) -> List[Contradiction]:
        """Report contradictions within the goal and among stored memories."""
        contradictions: List[Contradiction] = []
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a, b = claims[i].text, claims[j].text
                shared = _tokens(a) & _tokens(b)
                if shared and bool(_NEGATION.search(a)) != bool(_NEGATION.search(b)):
                    contradictions.append(
                        Contradiction(
                            description=f"clauses disagree: '{a}' vs '{b}'",
                            items=[a, b], source="goal",
                        )
                    )
        if self.retriever is not None and user_id:
            try:
                for conflict in self.retriever.conflicts(user_id):
                    contradictions.append(
                        Contradiction(
                            description=f"stored memories disagree on '{conflict.key}'",
                            items=list(conflict.values), source="memory",
                        )
                    )
            except Exception:
                pass
        return contradictions

    # -- entry point ----------------------------------------------------------

    def analyze(self, goal: str, user_id: int = 0) -> StructuredReasoningResult:
        """Produce the full structured picture of a goal."""
        self._user_id = user_id
        sub_problems = self.decompose(goal)
        claims = self.classify_claims(goal, user_id)
        missing = self.identify_missing(goal, claims)
        contradictions = self.find_contradictions(goal, claims, user_id)

        facts = [c for c in claims if c.kind == FACT]
        confidence = (len(facts) / len(claims)) if claims else 0.0
        if contradictions:
            confidence *= 0.5

        notes: List[str] = []
        injection = is_instruction_like(goal)
        if injection:
            notes.append("goal text contains instruction-like content; treated as untrusted data, not obeyed")
        if not facts and claims:
            notes.append("no claim is backed by verified evidence; nothing here is presented as fact")

        return StructuredReasoningResult(
            goal=goal,
            sub_problems=sub_problems,
            claims=claims,
            missing_information=missing,
            contradictions=contradictions,
            confidence=confidence,
            injection_flagged=injection,
            notes=notes,
        )
