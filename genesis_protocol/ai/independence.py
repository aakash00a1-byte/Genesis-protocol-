"""Is a council's agreement evidence, or just correlated error?

The council asks several models and reconciles their answers. That is useful for
coverage - a point one model misses, another may catch. It is *not* evidence of
truth, and the failure mode is specific: models share training corpora, shared
benchmarks and shared failure modes, so five models can agree and be wrong
together. Agreement between correlated members is one opinion repeated.

This module measures the two things that make agreement weak or strong:

* **independence** - are the members actually different? Same provider family,
  or an aggregator that fronts many models behind one API, means less.
* **shared sources** - if the members cite the same pages, they are not
  independent witnesses; they read the same book.

It returns an assessment, never a permission. ``is_evidence`` is always
``False``: consensus is not truth, whatever the numbers say. A high
``correlated_risk`` means the answer needs an independent check before anyone
treats it as established.

Stdlib only.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlparse

#: Provider -> model family. Two entries with the same family share training
#: lineage and therefore share failure modes.
_FAMILY = {
    "groq": "open-weights",
    "cerebras": "open-weights",
    "nvidia": "open-weights",
    "together": "open-weights",
    "huggingface": "open-weights",
    "openai": "openai",
    "gemini": "google",
    "google": "google",
    "mistral": "mistral",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
}

#: Providers that proxy many upstream models behind one endpoint. Their answers
#: may originate from the same model twice, so they count as less independent.
_AGGREGATORS = frozenset({"openrouter", "orcarouter", "freeai", "openai_compatible"})


def provider_family(provider: str, model: str = "") -> str:
    """Best-effort family for a provider/model pair."""
    p = (provider or "").strip().lower()
    if p in _AGGREGATORS:
        return "aggregator"
    if p in _FAMILY:
        return _FAMILY[p]
    m = (model or "").lower()
    for needle, family in (
        ("gpt", "openai"), ("o1", "openai"), ("o3", "openai"),
        ("gemini", "google"), ("gemma", "google"),
        ("claude", "anthropic"), ("mistral", "mistral"), ("ministral", "mistral"),
        ("llama", "open-weights"), ("qwen", "open-weights"), ("deepseek", "deepseek"),
    ):
        if needle in m:
            return family
    return p or "unknown"


def _tokens(text: str) -> set:
    return set("".join(c.lower() if c.isalnum() else " " for c in (text or "")).split())


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _domains(sources: Iterable[str]) -> set:
    out = set()
    for src in sources or ():
        try:
            host = urlparse(str(src)).netloc.lower()
        except ValueError:
            host = ""
        out.add(host or str(src).lower()[:60])
    return out


@dataclass
class ConsensusAssessment:
    """How much an agreement is worth. Never a grant, never a truth claim."""

    members: int = 0
    agreement: float = 0.0
    largest_cluster: int = 0
    independence: float = 0.0
    distinct_families: int = 0
    source_overlap: float = 0.0
    correlated_risk: str = "unknown"          # low | medium | high | unknown
    requires_independent_check: bool = True
    is_evidence: bool = False                 # always False, by design
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "members": self.members,
            "agreement": round(self.agreement, 3),
            "largest_cluster": self.largest_cluster,
            "independence": round(self.independence, 3),
            "distinct_families": self.distinct_families,
            "source_overlap": round(self.source_overlap, 3),
            "correlated_risk": self.correlated_risk,
            "requires_independent_check": self.requires_independent_check,
            "is_evidence": self.is_evidence,
            "reasons": list(self.reasons),
        }


def assess(members: Sequence, threshold: float = 0.6) -> ConsensusAssessment:
    """Assess an agreement among council members.

    Each member needs ``provider`` and ``content``; ``model`` and ``sources``
    are optional. Members with an error or no content are ignored, because a
    silent member is not a witness.
    """
    usable = [m for m in members or ()
              if not getattr(m, "error", None) and (getattr(m, "content", "") or "").strip()]
    if not usable:
        return ConsensusAssessment(
            reasons=["no usable member answered; there is nothing to agree on"],
            correlated_risk="unknown",
        )

    # Greedy clustering: each member joins the first cluster it resembles.
    clusters: list[list] = []
    for m in usable:
        for cluster in clusters:
            if _similarity(getattr(cluster[0], "content", ""), getattr(m, "content", "")) >= threshold:
                cluster.append(m)
                break
        else:
            clusters.append([m])

    largest = max(len(c) for c in clusters)
    agreement = largest / len(usable)
    families = [provider_family(getattr(m, "provider", ""), getattr(m, "model", "")) for m in usable]
    distinct = len(set(families))
    aggregators = sum(1 for f in families if f == "aggregator")
    # An aggregator contributes at most half an independent witness.
    effective = distinct - 0.5 * aggregators
    independence = max(0.0, min(1.0, effective / len(usable)))

    overlap = 0.0
    sources = [getattr(m, "sources", None) for m in usable]
    if any(sources):
        domain_sets = [_domains(s) for s in sources if s]
        if len(domain_sets) >= 2:
            first = domain_sets[0]
            worst = 0.0
            for other in domain_sets[1:]:
                if first or other:
                    worst = max(worst, len(first & other) / max(1, len(first | other)))
            overlap = worst

    reasons: list[str] = []
    reasons.append(f"{largest} of {len(usable)} answers fall in the same cluster "
                   f"(similarity >= {threshold})")
    if distinct < len(usable):
        reasons.append(f"{len(usable) - distinct} member(s) share a model family "
                       f"({distinct} distinct family/families across {len(usable)})")
    if aggregators:
        reasons.append(f"{aggregators} member(s) are aggregators, so their answers may "
                       "come from the same upstream model")
    if overlap >= 0.5:
        reasons.append(f"members cite overlapping sources (overlap {overlap:.2f})")

    if agreement >= 0.8 and (independence <= 0.5 or overlap >= 0.6):
        risk = "high"
        reasons.append("high agreement between correlated members - this is one opinion "
                       "repeated, not several independent confirmations")
    elif agreement >= 0.6 and independence <= 0.75:
        risk = "medium"
        reasons.append("agreement exists but independence is limited; an independent "
                       "check is required before treating it as established")
    else:
        risk = "low"
        reasons.append("agreement and independence are consistent with a genuine signal, "
                       "but agreement is still not proof")

    return ConsensusAssessment(
        members=len(usable),
        agreement=agreement,
        largest_cluster=largest,
        independence=independence,
        distinct_families=distinct,
        source_overlap=overlap,
        correlated_risk=risk,
        requires_independent_check=(risk != "low") or agreement >= 0.6,
        is_evidence=False,
        reasons=reasons,
    )


def describe(assessment: ConsensusAssessment | None) -> str:
    """One-line human summary, for logs and Telegram."""
    if assessment is None:
        return "consensus assessment: not run"
    return (
        f"consensus assessment: {assessment.largest_cluster}/{assessment.members} agree, "
        f"independence {assessment.independence:.2f}, correlated risk "
        f"{assessment.correlated_risk}, evidence: no"
    )
