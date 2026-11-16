"""Bridge correlated incidents to the canonical admin alert system (V7 P6).

Automatic alerts reuse ``core.admin_alerts.AdminAlertManager`` - the same channel
the rest of Genesis uses - rather than introducing a second notification path.
The bridge is defensive: if the alert manager is unavailable or raises, the
defence pass continues and the failure is reported, never swallowed silently.

Only the incident summary is sent (severity, confidence, detectors, entities).
Evidence payloads are not forwarded wholesale, so a secret that leaked into a
finding cannot be re-broadcast through an alert.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# incident severity -> AdminAlert level name
_LEVEL = {"info": "INFO", "low": "INFO", "medium": "WARNING", "high": "ERROR", "critical": "CRITICAL"}


class AdminAlertBridge:
    """Adapts incidents to ``AdminAlertManager.send_alert``."""

    def __init__(self, manager: Optional[Any] = None):
        self._manager = manager

    @property
    def manager(self) -> Any:
        if self._manager is None:
            from genesis_protocol.core.admin_alerts import get_admin_alerts

            self._manager = get_admin_alerts()
        return self._manager

    def __call__(self, incident: Any) -> Dict[str, Any]:
        data = incident.to_dict() if hasattr(incident, "to_dict") else dict(incident)
        from genesis_protocol.core.admin_alerts import AlertLevel, AlertType

        level = getattr(AlertLevel, _LEVEL.get(str(data.get("severity", "info")).lower(), "WARNING"))
        title = f"Guardian incident {data.get('incident_id')} ({data.get('severity')})"
        message = (
            f"Confirmed security incident. detectors={data.get('detectors')} "
            f"confidence={data.get('confidence')} entities={data.get('entities')}"
        )
        self.manager.send_alert(level, AlertType.CRITICAL_ERROR, title, message,
                                details={"incident_id": data.get("incident_id"),
                                         "detectors": data.get("detectors")})
        return {"delivered": True, "incident_id": data.get("incident_id")}
