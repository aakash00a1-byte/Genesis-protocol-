"""Genesis Protocol - AI Guardian & Self-Defence (V7 P5).

A security-first, **read-only** monitoring layer. It detects threats and
suspicious behaviour, records them in a tamper-evident log, and *recommends*
reversible responses for a human to approve. It never acts on its own.

Modules:

* ``events``      - append-only, hash-chained security event log (forensics).
* ``threat_intel``- advisories from CERT-In, CISA, NVD, OWASP and vendor sources,
                    with source links, timestamps and an explained confidence.
* ``detection``   - runtime threats: auth/webhook/API abuse, identity spoofing,
                    privilege escalation, secret exposure, unexpected tool runs.
* ``behaviour``   - per-agent behaviour: unusual tool patterns, policy violations,
                    repeated denials, grant escapes, identity/history correlation.
* ``health``      - resources, memory/database integrity, service failures and
                    unexpected production behaviour changes.
* ``response``    - reversible, owner-gated response recommendations only.
* ``guardian``    - the orchestrator that runs a read-only pass and records
                    evidence with an incident timeline.

Rules this package holds to:

* Reuse the canonical ``AgentPolicy``, ``ToolRegistry``, ``IdentityRegistry`` and
  ``AuditLog``; never duplicate them.
* READ-ONLY. No automatic account deletion, credential rotation, code
  modification, deployment or settings change.
* Any privileged response requires owner approval and is proposed, never taken.
* Never claim attribution the evidence does not support.
"""
from genesis_protocol.guardian.detection import Finding, RuntimeDetector
from genesis_protocol.guardian.events import SecurityEvent, SecurityEventLog, get_security_log
from genesis_protocol.guardian.guardian import Guardian, GuardianReport
from genesis_protocol.guardian.health import HealthFinding, HealthMonitor
from genesis_protocol.guardian.response import (
    FORBIDDEN_ACTIONS,
    PRIVILEGED_ACTIONS,
    DefensiveResponder,
    ResponseRecommendation,
)
from genesis_protocol.guardian.threat_intel import (
    TRUSTED_SOURCES,
    ThreatAdvisory,
    ThreatIntel,
)

__all__ = [
    "Finding",
    "RuntimeDetector",
    "SecurityEvent",
    "SecurityEventLog",
    "get_security_log",
    "Guardian",
    "GuardianReport",
    "HealthFinding",
    "HealthMonitor",
    "DefensiveResponder",
    "ResponseRecommendation",
    "FORBIDDEN_ACTIONS",
    "PRIVILEGED_ACTIONS",
    "ThreatAdvisory",
    "ThreatIntel",
    "TRUSTED_SOURCES",
]
