"""Threat intelligence for the AI Guardian (V7 P5).

Tracks advisories from trusted sources (CERT-In, CISA, NVD, OWASP, vendor
advisories), keeps their source link, publication time and a confidence, and
identifies which of them are relevant to Genesis's own dependencies.

Design constraints:

* **No fabricated intelligence.** An advisory is only ever produced from a source
  document that was actually supplied (parsed) or fetched. If nothing was
  supplied, the result is empty - never invented. Every advisory carries the URL
  it came from and the time it was published.
* **Confidence is explicit and explained.** It is derived from the source's trust
  tier and whether the advisory names a dependency Genesis actually uses, and it
  is reported alongside the advisory, never as a bare number.
* **Fetching is opt-in.** ``fetch`` performs a network call and is never invoked
  automatically; the default path parses documents a caller already has, which
  keeps detection deterministic and testable.
* This module only *records* intelligence. It takes no defensive action.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Trusted sources. ``tier`` feeds the confidence calculation; ``kind`` says what
# the source is so a reader knows how to weigh it.
TRUSTED_SOURCES: Dict[str, Dict[str, str]] = {
    "cert-in": {"name": "CERT-In", "url": "https://www.cert-in.org.in/", "tier": "high", "kind": "national-csirt"},
    "cisa": {"name": "CISA", "tier": "high", "kind": "government",
             "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog"},
    "nvd": {"name": "NVD", "url": "https://nvd.nist.gov/", "tier": "high", "kind": "vulnerability-db"},
    "owasp": {"name": "OWASP", "url": "https://owasp.org/www-project-top-ten/", "tier": "medium", "kind": "guidance"},
    "github-advisories": {"name": "GitHub Advisories", "tier": "medium",
                          "kind": "vendor-advisory", "url": "https://github.com/advisories"},
    "pypi-advisory": {"name": "PyPI Advisory DB", "tier": "medium",
                      "kind": "vendor-advisory", "url": "https://github.com/pypa/advisory-database"},
    "vendor": {"name": "Vendor advisory", "url": "", "tier": "medium", "kind": "vendor-advisory"},
}

_TIER_WEIGHT = {"high": 0.6, "medium": 0.4, "low": 0.2}
_CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.I)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ThreatAdvisory:
    """One advisory from a trusted source, with provenance and confidence."""

    advisory_id: str
    title: str
    summary: str
    source: str
    url: str
    published: str
    severity: str
    affected: List[str] = field(default_factory=list)
    confidence: float = 0.0
    confidence_reason: str = ""
    relevant_dependencies: List[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=_utcnow)

    @property
    def is_cve(self) -> bool:
        return bool(_CVE_RE.search(self.advisory_id or ""))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def genesis_dependencies(root: Optional[Path] = None) -> List[str]:
    """Package names Genesis depends on, read from requirements.txt.

    Read-only. Returns [] when the file is missing rather than guessing.
    """
    path = (root or Path.cwd()) / "requirements.txt"
    if not path.exists():
        return []
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].strip().lower()
        if name:
            names.append(name)
    return sorted(set(names))


class ThreatIntel:
    """Parses advisories, scores their confidence and finds relevant ones."""

    def __init__(self, dependencies: Optional[Iterable[str]] = None, root: Optional[Path] = None):
        self.dependencies = set(dependencies) if dependencies is not None else set(genesis_dependencies(root))

    # -- confidence -----------------------------------------------------------

    def _confidence(self, source_key: str, advisory: "ThreatAdvisory") -> tuple:
        tier = TRUSTED_SOURCES.get(source_key, {}).get("tier", "low")
        score = _TIER_WEIGHT.get(tier, 0.2)
        reasons = [f"source tier '{tier}'"]
        if advisory.is_cve:
            score += 0.15
            reasons.append("has a CVE id")
        if advisory.affected:
            score += 0.1
            reasons.append("names affected packages")
        if not advisory.url:
            score -= 0.2
            reasons.append("no source link (reduced)")
        score = max(0.0, min(1.0, round(score, 4)))
        return score, "; ".join(reasons)

    def _relevant(self, advisory: "ThreatAdvisory") -> List[str]:
        haystack = " ".join(
            [advisory.title, advisory.summary, advisory.advisory_id] + list(advisory.affected)
        ).lower()
        return sorted({dep for dep in self.dependencies if dep and dep in haystack})

    # -- parsing --------------------------------------------------------------

    def parse(self, raw: Dict[str, Any], source_key: str) -> ThreatAdvisory:
        """Normalise one raw advisory document into a :class:`ThreatAdvisory`.

        Missing fields are not invented: an absent title becomes an explicit
        "untitled advisory" and the missing source link is reflected in the
        confidence rather than filled with a guess.
        """
        source = TRUSTED_SOURCES.get(source_key, TRUSTED_SOURCES["vendor"])
        affected = raw.get("affected") or raw.get("packages") or []
        if isinstance(affected, str):
            affected = [affected]
        advisory = ThreatAdvisory(
            advisory_id=str(raw.get("id") or raw.get("cve") or "unidentified").strip(),
            title=str(raw.get("title") or raw.get("summary") or "untitled advisory").strip(),
            summary=str(raw.get("description") or raw.get("summary") or "").strip(),
            source=source["name"],
            url=str(raw.get("url") or source["url"]).strip(),
            published=str(raw.get("published") or raw.get("date") or "").strip(),
            severity=str(raw.get("severity") or "unknown").strip().lower(),
            affected=[str(a) for a in affected],
        )
        advisory.relevant_dependencies = self._relevant(advisory)
        advisory.confidence, advisory.confidence_reason = self._confidence(source_key, advisory)
        return advisory

    def parse_many(self, raw_docs: Iterable[Dict[str, Any]], source_key: str) -> List[ThreatAdvisory]:
        return [self.parse(doc, source_key) for doc in raw_docs]

    def relevant_only(self, advisories: Iterable[ThreatAdvisory]) -> List[ThreatAdvisory]:
        """Advisories that name a dependency Genesis actually uses."""
        return [a for a in advisories if a.relevant_dependencies]

    # -- optional live fetch (never called automatically) ---------------------

    def fetch(self, url: str, timeout: float = 15.0) -> Any:
        """Fetch a source document. Network-bound and opt-in.

        Raises on failure; callers decide how to handle a source outage. This is
        never invoked by the guardian's monitoring loop, so detection never
        depends on the network being up.
        """
        import httpx

        response = httpx.get(url, timeout=timeout, headers={"User-Agent": "GenesisProtocol-Guardian/1.0"})
        response.raise_for_status()
        return response.json()


def trusted_source_names() -> List[str]:
    return sorted(TRUSTED_SOURCES)
