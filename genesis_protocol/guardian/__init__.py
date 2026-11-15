"""Genesis Protocol - AI Guardian & Self-Defence (V7 P5 + P6).

A security-first monitoring and **bounded** defence layer.

P5 (read-only):

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
* ``guardian``    - the read-only orchestrator: monitor, forensics, timeline.

P6 (controlled autonomous defence):

* ``severity``    - normalises severity and attaches an *explained* confidence.
* ``correlation`` - clusters findings across agents/tools/identities/sessions.
* ``actions``     - the allow-list of permitted defensive actions (low risk only
                    may run automatically; every entry is reversible).
* ``budget``      - per-target cooldowns and global/consecutive action caps.
* ``killswitch``  - a persisted, fail-closed emergency stop.
* ``actionsink``  - reversible sinks for low-risk actions (temporary cooldowns).
* ``alerting``    - bridge to the canonical ``AdminAlertManager``.
* ``defence``     - the engine that performs bounded, reversible actions and
                    proposes everything else to the owner.

Rules this package holds to:

* Reuse the canonical ``AgentPolicy``, ``ToolRegistry``, ``IdentityRegistry`` and
  ``AuditLog``; never duplicate them.
* Never delete data, rotate a credential, modify code, deploy, change a trust
  root or permission threshold, or change its own authority.
* Only low-risk, reversible, allow-listed actions may run automatically, and only
  when the kill switch is off and the action budget allows it.
* Any privileged response requires owner approval and is proposed, never taken.
* Never claim attribution the evidence does not support.
"""
from genesis_protocol.guardian.actions import ALLOWED_ACTIONS, NEVER_ACTIONS, ActionCatalog, ActionSpec
from genesis_protocol.guardian.actionsink import LocalActionSink
from genesis_protocol.guardian.alerting import AdminAlertBridge
from genesis_protocol.guardian.budget import ActionBudget, BudgetDecision
from genesis_protocol.guardian.correlation import Correlator, Incident
from genesis_protocol.guardian.defence import DefenceEngine, DefenceReport
from genesis_protocol.guardian.detection import Finding, RuntimeDetector
from genesis_protocol.guardian.events import SecurityEvent, SecurityEventLog, get_security_log
from genesis_protocol.guardian.guardian import Guardian, GuardianReport
from genesis_protocol.guardian.health import HealthFinding, HealthMonitor
from genesis_protocol.guardian.killswitch import KillSwitch, get_kill_switch
from genesis_protocol.guardian.response import (
    FORBIDDEN_ACTIONS,
    PRIVILEGED_ACTIONS,
    DefensiveResponder,
    ResponseRecommendation,
)
from genesis_protocol.guardian.severity import ClassifiedFinding, SeverityClassifier
from genesis_protocol.guardian.threat_intel import (
    TRUSTED_SOURCES,
    ThreatAdvisory,
    ThreatIntel,
)

__all__ = [
    # P5
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
    # P6
    "SeverityClassifier",
    "ClassifiedFinding",
    "Correlator",
    "Incident",
    "ActionCatalog",
    "ActionSpec",
    "ALLOWED_ACTIONS",
    "NEVER_ACTIONS",
    "ActionBudget",
    "BudgetDecision",
    "KillSwitch",
    "get_kill_switch",
    "LocalActionSink",
    "AdminAlertBridge",
    "DefenceEngine",
    "DefenceReport",
]
