"""The AI Guardian: read-only monitoring, detection and forensics (V7 P5).

The guardian observes. It runs the detectors, records every finding as a
tamper-evident security event, builds incident timelines, and proposes reversible
responses for a human to approve. It never takes a defensive action, never
changes a permission, never rotates a credential and never deploys.

It composes the canonical systems and adds nothing that duplicates them:

* ``guardian.events.SecurityEventLog`` - tamper-evident forensic record.
* ``guardian.threat_intel.ThreatIntel`` - advisories from trusted sources.
* ``guardian.detection.RuntimeDetector`` - runtime threats.
* ``guardian.behaviour.BehaviourMonitor`` - per-agent behaviour.
* ``guardian.health.HealthMonitor`` - resources and database integrity.
* ``guardian.response.DefensiveResponder`` - reversible recommendations only.
* ``agentic.audit`` / ``identity_registry`` / ``policy`` / ``tools`` / ``trust``
  are read through those modules, never re-implemented here.

Attribution rule: a finding states what was observed and how confident the
detector is. The guardian never asserts who is responsible beyond the identifiers
the audit log itself records, and never claims attribution the evidence does not
support.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from genesis_protocol.guardian.behaviour import BehaviourMonitor
from genesis_protocol.guardian.detection import Finding, RuntimeDetector
from genesis_protocol.guardian.events import SecurityEventLog, get_security_log
from genesis_protocol.guardian.health import HealthMonitor
from genesis_protocol.guardian.response import DefensiveResponder
from genesis_protocol.guardian.threat_intel import ThreatAdvisory, ThreatIntel

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GuardianReport:
    """The outcome of one monitoring pass."""

    started_at: str
    finished_at: str
    findings: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    threat_advisories: List[Dict[str, Any]]
    chain: Dict[str, Any]
    read_only: bool = True
    actions_taken: List[str] = field(default_factory=list)

    def highest_severity(self) -> str:
        if not self.findings:
            return "info"
        return max((f.get("severity", "info") for f in self.findings), key=lambda s: SEVERITY_ORDER.get(s, 0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "read_only": self.read_only,
            "actions_taken": self.actions_taken,
            "highest_severity": self.highest_severity(),
            "finding_count": len(self.findings),
            "findings": self.findings,
            "recommendations": self.recommendations,
            "threat_advisories": self.threat_advisories,
            "chain": self.chain,
        }


class Guardian:
    """Read-only security monitor and forensics recorder."""

    def __init__(
        self,
        security_log: Optional[SecurityEventLog] = None,
        detector: Optional[RuntimeDetector] = None,
        behaviour: Optional[BehaviourMonitor] = None,
        health: Optional[HealthMonitor] = None,
        responder: Optional[DefensiveResponder] = None,
        threat_intel: Optional[ThreatIntel] = None,
    ):
        self.security_log = security_log or get_security_log()
        self.detector = detector or RuntimeDetector(security_log=self.security_log)
        self.behaviour = behaviour or BehaviourMonitor()
        self.health = health or HealthMonitor()
        self.responder = responder or DefensiveResponder()
        self.threat_intel = threat_intel or ThreatIntel()

    # -- recording ------------------------------------------------------------

    def record_finding(self, finding: Any) -> Dict[str, Any]:
        """Persist a finding as a tamper-evident security event."""
        data = finding.to_dict() if hasattr(finding, "to_dict") else dict(finding)
        category = data.get("category") or ("behaviour" if "agent_id" in data else "health")
        if category not in ("auth", "webhook", "api", "identity", "privilege", "secret",
                            "tool", "behaviour", "health", "integrity", "anomaly"):
            category = "anomaly"
        event = self.security_log.record(
            category=category,
            event=data.get("detector", "finding"),
            severity=data.get("severity", "info"),
            actor=data.get("actor") or data.get("agent_id"),
            subject=data.get("subject"),
            evidence={
                "title": data.get("title"),
                "description": data.get("description"),
                "confidence": data.get("confidence"),
                "measured": data.get("measured"),
                "evidence": data.get("evidence"),
            },
        )
        return event.to_dict()

    # -- monitoring pass ------------------------------------------------------

    def monitor(
        self,
        observations: Optional[List[Dict[str, Any]]] = None,
        advisories: Optional[List[ThreatAdvisory]] = None,
        record: bool = True,
    ) -> GuardianReport:
        """Run one full read-only monitoring pass.

        ``observations`` is a caller-supplied stream of runtime events (auth,
        webhook, api, secret payloads). It is optional: without it, the guardian
        still scans the canonical audit log, agent behaviour and system health.
        """
        started = _utcnow()
        findings: List[Finding] = []

        # Runtime threats from the audit log.
        findings += self.detector.scan_audit()
        # Runtime threats from supplied observations (and the guardian's own log).
        if observations:
            findings += self.detector.scan_observations(observations)
        # Agent behaviour.
        findings += self.behaviour.monitor()
        # System health.
        findings += self.health.check()

        if record:
            for finding in findings:
                self.record_finding(finding)

        recommendations = self.responder.recommend_many(findings)
        if record:
            for rec in recommendations:
                self.security_log.record(
                    category="response", event=f"recommend:{rec.action}", severity="info",
                    actor=rec.target, evidence=rec.to_dict(),
                )

        return GuardianReport(
            started_at=started,
            finished_at=_utcnow(),
            findings=[f.to_dict() for f in findings],
            recommendations=[r.to_dict() for r in recommendations],
            threat_advisories=[a.to_dict() for a in (advisories or [])],
            chain=self.security_log.verify(),
            read_only=True,
            actions_taken=[],
        )

    # -- forensics ------------------------------------------------------------

    def incident_timeline(self, actor: Optional[str] = None) -> Dict[str, Any]:
        """A time-ordered evidence trail, with the chain integrity at the top."""
        return {
            "chain": self.security_log.verify(),
            "actor": actor,
            "events": self.security_log.incident_timeline(actor=actor),
            "note": "events are recorded as observed; the guardian asserts no attribution beyond recorded identifiers",
        }

    def verify_chain(self) -> Dict[str, Any]:
        return self.security_log.verify()

    def status(self) -> Dict[str, Any]:
        """A compact, read-only status summary."""
        return {
            "read_only": True,
            "autonomous_actions": [],
            "security_events": self.security_log.count(),
            "chain": self.security_log.verify(),
            "categories": {
                c: self.security_log.count(c)
                for c in ("auth", "identity", "privilege", "secret", "tool", "behaviour", "health")
            },
        }

    # -- threat intelligence --------------------------------------------------

    def assess_advisories(self, raw_docs: List[Dict[str, Any]], source_key: str) -> Dict[str, Any]:
        """Parse advisories and return the ones relevant to Genesis dependencies.

        Recording them to the forensic log is opt-in via ``record``.
        """
        advisories = self.threat_intel.parse_many(raw_docs, source_key)
        relevant = self.threat_intel.relevant_only(advisories)
        return {
            "source": source_key,
            "total": len(advisories),
            "relevant": [a.to_dict() for a in relevant],
            "all": [a.to_dict() for a in advisories],
        }

    def record_advisories(self, advisories: List[ThreatAdvisory]) -> int:
        for advisory in advisories:
            self.security_log.record(
                category="threat_intel", event="advisory", severity=advisory.severity or "info",
                subject=advisory.advisory_id,
                evidence={
                    "title": advisory.title, "source": advisory.source, "url": advisory.url,
                    "published": advisory.published, "confidence": advisory.confidence,
                    "confidence_reason": advisory.confidence_reason,
                    "relevant_dependencies": advisory.relevant_dependencies,
                },
            )
        return len(advisories)
