"""Relevance filtering helpers."""
from __future__ import annotations

import re

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "is", "are", "was", "were", "be", "been", "it", "this", "that", "as",
    "at", "by", "from", "we", "you", "they", "our", "your", "their",
}

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokens(text: str) -> set[str]:
    if not text:
        return set()
    tokens = _TOKEN_RE.findall(text.lower())
    return {t for t in tokens if t not in _STOP and len(t) > 1}


def keyword_relevance(query: str, document: str, *, max_tokens: int = 1024) -> float:
    """Simple offline relevance score in [0, 1].

    0 if no meaningful tokens overlap, otherwise the Dice coefficient of the
    overlapping token sets. Deterministic and dependency-free so it can run
    fully offline.
    """
    q = _tokens(query)
    d = _tokens(document)
    if not q or not d:
        return 0.0
    overlap = q & d
    if not overlap:
        return 0.0
    return (2.0 * len(overlap)) / (len(q) + len(d))