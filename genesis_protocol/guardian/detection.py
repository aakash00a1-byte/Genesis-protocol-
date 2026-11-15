"""Runtime threat detection for the AI Guardian (V7 P5).

Detects suspicious runtime activity by reading the records the system already
keeps and cross-checking them against the canonical registries. It composes -
never duplicates - the existing security machinery:

* ``agentic.audit.AuditLog`` - the source of tool decisions and outcomes.
* ``agentic.identity_registry.IdentityRegistry`` - the authority on which agents
  exist and whether they are active.
* ``agentic.policy.AgentPolicy`` / ``PRIVILEGED_OPERATIONS`` - the authority on
  what is privileged.
* ``tools.tool_registry.ToolRegistry`` - the authority on which tools exist.

What it looks for:

* suspicious authentication attempts (repeated failures per actor),
* webhook abuse (repeated invalid or flood webhook calls),
* unusual API activity (request rate spikes),
* agent identity spoofing (an agent id that is unknown, inactive, or whose
  credential does not belong to it),
* privilege escalation attempts (restricted/admin tool requests by non-owners,
  or attempts at privileged operations),
* secret exposure (secret-shaped strings in observed payloads),
* unexpected tool execution (a tool executed that is not in the registry, or
  executed without a preceding allowed request).

Every detector is read-only and deterministic. Thresholds are explicit module
constants so a reviewer can see exactly when a finding fires. Nothing here
changes state, denies a request, or takes a defensive action.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from genesis_protocol.agentic.audit import AuditLog, get_audit_log
from genesis_protocol.agentic.policy import PRIVILEGED_OPERATIONS
from genesis_protocol.guardian.events import SecurityEventLog, get_security_log

# Thresholds. Named and central so the firing conditions are reviewable.
AUTH_FAILURE_THRESHOLD = 5        # failed auth events for one actor in a window
WEBHOOK_ABUSE_THRESHOLD = 5       # invalid/rejected webhook calls for one source
API_BURST_THRESHOLD = 60          # API events for one actor in a window
DENIED_TOOL_THRESHOLD = 3         # denied tool requests for one actor in a window

# Secret-shaped strings. Deliberately conservative to limit false positives:
# a known prefix or a long high-entropy key: value assignment.
_SECRET_PATTERNS = re.compile(
    r"(?i)("
    r"gh[pousr]_[A-Za-z0-9]{20,}|"          # GitHub tokens
    r"hf_[A-Za-z0-9]{20,}|"                  # Hugging Face tokens
    r"sk-[A-Za-z0-9]{20,}|"                  # OpenAI-style keys
    r"AKIA[0-9A-Z]{16}|"                     # AWS access key id
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"   # PEM private key
    r"(?:api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*[^\s'\"]{12,}"
    r")"
)

SEVERITIES = ("info", "low", "medium", "high", "critical")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Finding:
    """One detection: what was seen, how sure we are, and the evidence."""

    detector: str
    category: str
    severity: str
    title: str
    description: str
    actor: Optional[str] = None
    subject: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    detected_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeDetector:
    """Read-only runtime detectors over audit, security and observation streams."""

    def __init__(
        self,
        audit: Optional[AuditLog] = None,
        security_log: Optional[SecurityEventLog] = None,
        identity_registry: Optional[Any] = None,
        tool_registry: Optional[Any] = None,
    ):
        self.audit = audit or get_audit_log()
        self.security_log = security_log or get_security_log()
        self._identities = identity_registry
        self._tools = tool_registry

    @property
    def identities(self) -> Any:
        if self._identities is None:
            from genesis_protocol.agentic.identity_registry import get_identity_registry

            self._identities = get_identity_registry()
        return self._identities

    @property
    def tools(self) -> Any:
        if self._tools is None:
            from genesis_protocol.tools.tool_registry import get_tool_registry

            self._tools = get_tool_registry()
        return self._tools

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _count_by(events: Iterable[Dict[str, Any]], key: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for event in events:
            value = event.get(key)
            if value is None:
                continue
            counts[str(value)] = counts.get(str(value), 0) + 1
        return counts

    @staticmethod
    def find_secrets(text: str) -> List[str]:
        """Return the secret-shaped substrings in ``text`` (never the value itself)."""
        return [m.group(0)[:12] + "…" for m in _SECRET_PATTERNS.finditer(text or "")]

    # -- authentication / webhook / API --------------------------------------

    def detect_auth(self, events: Iterable[Dict[str, Any]]) -> List[Finding]:
        failures = [e for e in events if e.get("event") in ("login_failed", "auth_failed")
                    or (e.get("category") == "auth" and e.get("event") == "failure")]
        findings = []
        for actor, count in self._count_by(failures, "actor").items():
            if count >= AUTH_FAILURE_THRESHOLD:
                findings.append(Finding(
                    detector="auth_bruteforce", category="auth",
                    severity="high" if count >= AUTH_FAILURE_THRESHOLD * 2 else "medium",
                    title=f"repeated authentication failures for '{actor}'",
                    description=f"{count} failed authentication attempts for the same actor",
                    actor=actor, evidence={"count": count, "threshold": AUTH_FAILURE_THRESHOLD},
                    confidence=min(0.95, 0.5 + 0.05 * count),
                ))
        return findings

    def detect_webhook_abuse(self, events: Iterable[Dict[str, Any]]) -> List[Finding]:
        abuse = [e for e in events if e.get("category") == "webhook"
                 and e.get("event") in ("rejected", "invalid_secret", "flood")]
        findings = []
        for source, count in self._count_by(abuse, "actor").items():
            if count >= WEBHOOK_ABUSE_THRESHOLD:
                findings.append(Finding(
                    detector="webhook_abuse", category="webhook",
                    severity="high" if count >= WEBHOOK_ABUSE_THRESHOLD * 2 else "medium",
                    title=f"webhook abuse from '{source}'",
                    description=f"{count} rejected or invalid webhook calls from the same source",
                    actor=source, evidence={"count": count, "threshold": WEBHOOK_ABUSE_THRESHOLD},
                    confidence=min(0.9, 0.5 + 0.05 * count),
                ))
        return findings

    def detect_api_burst(self, events: Iterable[Dict[str, Any]]) -> List[Finding]:
        api = [e for e in events if e.get("category") == "api"]
        findings = []
        for actor, count in self._count_by(api, "actor").items():
            if count >= API_BURST_THRESHOLD:
                findings.append(Finding(
                    detector="api_burst", category="api", severity="medium",
                    title=f"unusual API activity from '{actor}'",
                    description=f"{count} API calls from one actor, above the burst threshold",
                    actor=actor, evidence={"count": count, "threshold": API_BURST_THRESHOLD},
                    confidence=0.6,
                ))
        return findings

    # -- identity / privilege -------------------------------------------------

    def detect_identity_spoofing(self, audit_entries: Iterable[Dict[str, Any]]) -> List[Finding]:
        """An agent id seen in the audit that the identity registry does not vouch for."""
        findings = []
        seen: Dict[str, int] = {}
        for entry in audit_entries:
            agent_id = entry.get("agent_id")
            if not agent_id:
                continue
            seen[agent_id] = seen.get(agent_id, 0) + 1
        for agent_id, count in seen.items():
            verification = self.identities.verify(agent_id)
            if not verification.ok:
                findings.append(Finding(
                    detector="identity_spoofing", category="identity", severity="high",
                    title=f"unverified agent identity '{agent_id}' in audit history",
                    description=(
                        f"agent '{agent_id}' appears in {count} audit events "
                        f"but does not verify: {verification.reason}"
                    ),
                    actor=agent_id, subject=agent_id,
                    evidence={"count": count, "verify_reason": verification.reason},
                    confidence=0.85,
                ))
        return findings

    def detect_privilege_escalation(self, audit_entries: Iterable[Dict[str, Any]]) -> List[Finding]:
        """Denied privileged/restricted tool requests, and attempts at privileged ops."""
        findings = []
        denied: Dict[str, int] = {}
        escalated: set = set()
        for entry in audit_entries:
            tool = str(entry.get("tool") or "")
            reason = str(entry.get("reason") or "")
            actor = str(entry.get("agent_id") or entry.get("user_id") or "unknown")
            if entry.get("allowed") is False:
                denied[actor] = denied.get(actor, 0) + 1
            privileged = tool in PRIVILEGED_OPERATIONS or any(
                op in tool or op in reason for op in PRIVILEGED_OPERATIONS
            )
            # One finding per (actor, tool) so a single denied request - which can
            # appear as more than one audit entry - is not counted twice.
            key = (actor, tool or reason)
            if privileged and entry.get("allowed") is False and key not in escalated:
                escalated.add(key)
                findings.append(Finding(
                    detector="privilege_escalation", category="privilege", severity="high",
                    title=f"privileged operation attempt by '{actor}'",
                    description=f"attempt to perform privileged operation '{tool or reason}' was denied",
                    actor=actor, subject=tool or None,
                    evidence={"tool": tool, "reason": reason},
                    confidence=0.9,
                ))
        for actor, count in denied.items():
            if count >= DENIED_TOOL_THRESHOLD:
                findings.append(Finding(
                    detector="repeated_denials", category="privilege", severity="medium",
                    title=f"repeated denied actions by '{actor}'",
                    description=f"{count} denied tool requests for the same actor",
                    actor=actor, evidence={"count": count, "threshold": DENIED_TOOL_THRESHOLD},
                    confidence=0.7,
                ))
        return findings

    # -- secrets / tools ------------------------------------------------------

    def detect_secret_exposure(self, events: Iterable[Dict[str, Any]]) -> List[Finding]:
        findings = []
        for event in events:
            blob = " ".join(str(v) for v in (event.get("evidence") or {}).values())
            blob += " " + str(event.get("detail") or "")
            hits = self.find_secrets(blob)
            if hits:
                findings.append(Finding(
                    detector="secret_exposure", category="secret", severity="critical",
                    title="secret-shaped value observed in a runtime payload",
                    description="a value matching a known secret format appeared in an observed payload",
                    actor=str(event.get("actor") or "") or None,
                    evidence={"matched_kinds": hits, "count": len(hits)},
                    confidence=0.75,
                ))
        return findings

    def detect_unexpected_tool_execution(
        self, audit_entries: Iterable[Dict[str, Any]]
    ) -> List[Finding]:
        """A tool executed that is not in the registry, or executed after a denial."""
        findings = []
        known = set()
        try:
            known = {t.name for t in self.tools.get_all_tools()}
        except Exception:
            known = set()
        last_decision: Dict[tuple, bool] = {}
        for entry in audit_entries:
            agent = str(entry.get("agent_id") or entry.get("user_id") or "unknown")
            tool = str(entry.get("tool") or "")
            event = entry.get("event")
            if event == "tool_request":
                # Denial is tracked per (agent, tool): a denial of one tool must
                # not make an unrelated tool look like it ran after a denial.
                last_decision[(agent, tool)] = bool(entry.get("allowed"))
            elif event == "tool_result" and tool:
                if known and tool not in known:
                    findings.append(Finding(
                        detector="unregistered_tool", category="tool", severity="high",
                        title=f"execution of unregistered tool '{tool}'",
                        description="a tool result was recorded for a tool not present in the registry",
                        actor=agent, subject=tool, evidence={"tool": tool},
                        confidence=0.85,
                    ))
                if last_decision.get((agent, tool)) is False:
                    findings.append(Finding(
                        detector="execution_after_denial", category="tool", severity="critical",
                        title=f"tool '{tool}' executed after a denial",
                        description="a tool produced a result although the preceding request was denied",
                        actor=agent, subject=tool, evidence={"tool": tool},
                        confidence=0.9,
                    ))
        return findings

    # -- entry points ---------------------------------------------------------

    def scan_audit(self, limit: int = 1000) -> List[Finding]:
        """Run every audit-derived detector over the canonical audit log."""
        try:
            entries = self.audit.tail(limit)
        except Exception:
            entries = []
        findings: List[Finding] = []
        findings += self.detect_identity_spoofing(entries)
        findings += self.detect_privilege_escalation(entries)
        findings += self.detect_unexpected_tool_execution(entries)
        return findings

    def scan_observations(self, events: Iterable[Dict[str, Any]]) -> List[Finding]:
        """Run every observation-derived detector over a stream of runtime events."""
        events = list(events)
        findings: List[Finding] = []
        findings += self.detect_auth(events)
        findings += self.detect_webhook_abuse(events)
        findings += self.detect_api_burst(events)
        findings += self.detect_secret_exposure(events)
        return findings

    def scan_security_log(self, limit: int = 1000) -> List[Finding]:
        """Run the observation detectors over the guardian's own event log."""
        return self.scan_observations(self.security_log.entries(limit))
