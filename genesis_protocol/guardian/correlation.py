"""Security event correlation across agents, tools, identities and sessions.

Individual findings are noisy. P6 groups them into **incidents**: clusters of
findings that share an entity (actor, identity, tool or session) within a time
window. A cluster is evidence that several weak signals belong to one campaign,
and its aggregate confidence is what justifies an automated response.

Correlation is pure and deterministic: it reads findings (and, optionally, audit
entries to attribute sessions) and never mutates state or takes an action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from genesis_protocol.guardian.severity import SEVERITY_RANK, ClassifiedFinding, clamp

DEFAULT_WINDOW_SECONDS = 900  # 15 minutes


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


@dataclass
class Incident:
    """A correlated cluster of findings."""

    incident_id: str
    entities: Dict[str, List[str]]
    detectors: List[str]
    severity: str
    confidence: float
    findings: List[Dict[str, Any]]
    opened_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Correlator:
    """Clusters classified findings that share an entity within a time window."""

    def __init__(self, window_seconds: int = DEFAULT_WINDOW_SECONDS):
        self.window_seconds = window_seconds

    @staticmethod
    def _entities_of(data: Dict[str, Any]) -> Dict[str, List[str]]:
        out: Dict[str, List[str]] = {}
        for key, name in (("actor", "actor"), ("agent_id", "identity"),
                          ("subject", "subject"), ("session", "session"), ("tool", "tool")):
            value = data.get(key)
            if value:
                out.setdefault(name, [])
                if str(value) not in out[name]:
                    out[name].append(str(value))
        evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
        if evidence.get("tool"):
            out.setdefault("tool", [])
            if str(evidence["tool"]) not in out["tool"]:
                out["tool"].append(str(evidence["tool"]))
        return out

    def correlate(
        self,
        findings: Iterable[ClassifiedFinding],
        window_seconds: Optional[int] = None,
    ) -> List[Incident]:
        window = self.window_seconds if window_seconds is None else window_seconds
        items: List[Tuple[ClassifiedFinding, Dict[str, List[str]], Optional[float]]] = []
        for finding in findings:
            data = finding.to_dict()
            items.append((finding, self._entities_of(data), _parse_ts(data.get("classified_at"))))

        # Union-find over findings that share any entity key/value within the window.
        parent = list(range(len(items)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)

        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                _, ei, ti = items[i]
                _, ej, tj = items[j]
                if ti is not None and tj is not None and abs(ti - tj) > window:
                    continue
                shared = False
                for name, values in ei.items():
                    if name in ej and set(values) & set(ej[name]):
                        shared = True
                        break
                if shared:
                    union(i, j)

        clusters: Dict[int, List[int]] = {}
        for idx in range(len(items)):
            clusters.setdefault(find(idx), []).append(idx)

        incidents: List[Incident] = []
        for n, (_, members) in enumerate(sorted(clusters.items())):
            member_findings = [items[m][0] for m in members]
            entities: Dict[str, List[str]] = {}
            for m in members:
                for name, values in items[m][1].items():
                    entities.setdefault(name, [])
                    for v in values:
                        if v not in entities[name]:
                            entities[name].append(v)
            detectors = sorted({f.detector for f in member_findings})
            severity = max((f.severity for f in member_findings), key=lambda s: SEVERITY_RANK.get(s, 0))
            # Aggregate confidence: strongest member, nudged up by corroboration.
            top = max(f.confidence for f in member_findings)
            bonus = 0.10 * (len(detectors) - 1)
            confidence = clamp(round(top + bonus, 3))
            timestamps = sorted(t for t in (items[m][2] for m in members) if t is not None)
            opened = (datetime.fromtimestamp(timestamps[0], tz=timezone.utc).isoformat()
                      if timestamps else _utcnow())
            updated = (datetime.fromtimestamp(timestamps[-1], tz=timezone.utc).isoformat()
                       if timestamps else _utcnow())
            incidents.append(Incident(
                incident_id=f"INC-{n + 1:04d}",
                entities=entities,
                detectors=detectors,
                severity=severity,
                confidence=confidence,
                findings=[f.to_dict() for f in member_findings],
                opened_at=opened,
                updated_at=updated,
            ))
        incidents.sort(key=lambda i: (SEVERITY_RANK.get(i.severity, 0), i.confidence), reverse=True)
        return incidents

    @staticmethod
    def attribute_sessions(findings: List[Dict[str, Any]], audit_entries: Iterable[Dict[str, Any]]) -> None:
        """Fill a ``session`` field on findings from the audit log, in place.

        A session is taken from the most recent audit entry for the same actor.
        This lets findings from different interfaces join one incident when they
        belong to one interaction, without inventing a session id.
        """
        latest: Dict[str, str] = {}
        for entry in audit_entries:
            actor = str(entry.get("agent_id") or entry.get("user_id") or "")
            session = entry.get("session") or entry.get("session_id")
            if actor and session:
                latest[actor] = str(session)
        for finding in findings:
            actor = str(finding.get("actor") or finding.get("agent_id") or "")
            if actor and not finding.get("session") and actor in latest:
                finding["session"] = latest[actor]
