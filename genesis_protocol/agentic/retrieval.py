"""Context-aware memory retrieval with conflict and staleness detection (V7 P3).

``AgentMemory.recall`` already returns keyword-relevant rows for one user. This
module adds the judgement layer on top:

* rank candidate memories by relevance, verification status, confidence and
  freshness, and explain the score;
* detect *conflicts* - items whose content overlaps but whose assertions
  disagree (e.g. two different values for the same key), and never silently pick
  one;
* detect *stale* items by age or by an explicit ``expires_at``;
* assemble a prompt-safe context block that labels every item with its
  provenance and flags conflicts, using ``memory_safety.render_recall_block``.

Nothing here writes to memory or grants a permission. It reads, ranks and
reports; a conflict is surfaced to the caller (and the owner), never resolved by
overwriting one side with the other.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from genesis_protocol.agentic.memory import AgentMemory
from genesis_protocol.agentic.memory_safety import is_instruction_like, render_recall_block

# Higher is more trustworthy. Used only to order and to label, never to allow.
_VERIFICATION_WEIGHT = {
    "verified": 1.0,
    "user_provided": 0.7,
    "hypothesis": 0.4,
    "unverified": 0.25,
}

DEFAULT_STALE_AFTER_DAYS = 90

# A short "key: value" or "key is value" assertion, used to spot two memories
# that talk about the same key but disagree on the value.
_ASSERTION = re.compile(r"^\s*([\w][\w \-]{1,40}?)\s*(?::|=|\bis\b|\bare\b)\s*(.+)$", re.I)


@dataclass
class ScoredMemory:
    memory: Dict[str, Any]
    score: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"memory": self.memory, "score": round(self.score, 4), "reasons": self.reasons}


@dataclass
class Conflict:
    key: str
    values: List[str]
    memory_ids: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "values": self.values, "memory_ids": self.memory_ids}


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_days(memory: Dict[str, Any]) -> float:
    created = _parse_ts(memory.get("created_at"))
    if created is None:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 86400.0)


def _keyword_overlap(query: str, content: str) -> int:
    terms = {t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 2}
    if not terms:
        return 0
    text = (content or "").lower()
    return sum(1 for t in terms if t in text)


class MemoryRetriever:
    """Read-only retrieval, ranking and conflict detection over one user's memory."""

    def __init__(
        self,
        memory: Optional[AgentMemory] = None,
        stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
    ):
        self.memory = memory or AgentMemory()
        self.stale_after_days = int(stale_after_days)

    # -- ranking --------------------------------------------------------------

    def search(
        self, user_id: int, query: str = "", limit: int = 10
    ) -> List[ScoredMemory]:
        """Return the most relevant memories for ``query``, ranked and explained."""
        candidates = self.memory.recall(user_id, query, limit=100)
        scored: List[ScoredMemory] = []
        for mem in candidates:
            overlap = _keyword_overlap(query, mem.get("content", ""))
            verification = _VERIFICATION_WEIGHT.get(str(mem.get("verification")), 0.25)
            try:
                confidence = float(mem.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            age = _age_days(mem)
            freshness = max(0.0, 1.0 - (age / max(1.0, self.stale_after_days)))
            score = (2.0 * overlap) + (1.5 * verification) + (1.0 * confidence) + (0.5 * freshness)
            reasons = [
                f"keyword_overlap={overlap}",
                f"verification={mem.get('verification')}",
                f"confidence={round(confidence, 2)}",
                f"age_days={round(age, 1)}",
            ]
            if is_instruction_like(str(mem.get("content", ""))):
                reasons.append("instruction_like=true")
            scored.append(ScoredMemory(memory=mem, score=score, reasons=reasons))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[: max(1, min(int(limit), 100))]

    # -- staleness ------------------------------------------------------------

    def stale(self, user_id: int) -> List[Dict[str, Any]]:
        """Return memories that are expired or older than the staleness window."""
        out = []
        for mem in self.memory.list_memories(user_id):
            expires_at = _parse_ts(mem.get("expires_at"))
            if expires_at is not None and expires_at < datetime.now(timezone.utc):
                out.append(mem)
            elif _age_days(mem) > self.stale_after_days:
                out.append(mem)
        return out

    # -- conflicts ------------------------------------------------------------

    @staticmethod
    def _assertion(content: str) -> Optional[Tuple[str, str]]:
        match = _ASSERTION.match(content or "")
        if not match:
            return None
        key = match.group(1).strip().lower()
        value = match.group(2).strip().lower()
        if not key or not value:
            return None
        return key, value

    def conflicts(self, user_id: int, kind: Optional[str] = None) -> List[Conflict]:
        """Group same-key assertions and report the keys whose values disagree.

        Two memories about the same key with the same value are agreement, not a
        conflict. The detector never edits either side; it only reports.
        """
        by_key: Dict[str, List[Tuple[str, str]]] = {}
        for mem in self.memory.list_memories(user_id, kind=kind):
            parsed = self._assertion(str(mem.get("content", "")))
            if parsed is None:
                continue
            key, value = parsed
            by_key.setdefault(key, []).append((value, mem.get("id", "")))
        conflicts: List[Conflict] = []
        for key, pairs in by_key.items():
            values = sorted({v for v, _ in pairs})
            if len(values) > 1:
                conflicts.append(
                    Conflict(key=key, values=values, memory_ids=[i for _, i in pairs])
                )
        return conflicts

    # -- prompt-safe context --------------------------------------------------

    def build_context(
        self, user_id: int, query: str = "", limit: int = 5
    ) -> str:
        """Assemble an untrusted-data context block from the top-ranked memories.

        Returns "" when there is nothing to show, so a caller can append only
        when there is content. Conflicts are noted so the model does not silently
        trust one side.
        """
        ranked = self.search(user_id, query, limit=limit)
        if not ranked:
            return ""
        items = [s.memory for s in ranked]
        block = render_recall_block(items)
        conflicts = self.conflicts(user_id)
        if conflicts:
            lines = [block, "", "Note: stored memories conflict on the following keys; do not assume either value:"]
            for conflict in conflicts:
                lines.append(f'- "{conflict.key}": {", ".join(conflict.values)}')
            block = "\n".join(lines)
        return block
