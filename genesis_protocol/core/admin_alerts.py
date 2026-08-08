"""Genesis Protocol - Admin Alert System

Sends critical alerts to Telegram admin only:
- Server status alerts
- Deployment alerts
- API failures
- Provider outages
- High usage/cost warnings
- Critical system errors
"""

import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from queue import Queue
import threading

from genesis_protocol.utils.logger import get_logger

logger = get_logger("core.admin_alerts")


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of admin alerts."""
    SERVER_STATUS = "server_status"
    DEPLOYMENT = "deployment"
    API_FAILURE = "api_failure"
    PROVIDER_OUTAGE = "provider_outage"
    HIGH_USAGE = "high_usage"
    HIGH_COST = "high_cost"
    CRITICAL_ERROR = "critical_error"
    SYSTEM_WARNING = "system_warning"


@dataclass
class AdminAlert:
    """Admin alert message."""
    level: AlertLevel
    alert_type: AlertType
    title: str
    message: str
    details: Optional[Dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sent: bool = False


class AdminAlertManager:
    """
    Manages admin alerts for Telegram.
    
    Only sends to Telegram admin channel.
    Never sends to web users.
    """
    
    def __init__(self):
        """Initialize alert manager."""
        self.logger = logging.getLogger("core.admin_alerts")
        self._alert_queue: Queue = Queue()
        self._alert_history: List[AdminAlert] = []
        self._admin_chat_id: Optional[int] = None
        self._enabled: bool = True
        self._sender: Optional[callable] = None
        self._alert_thread: Optional[threading.Thread] = None
        self._running: bool = False
    
    def set_admin_chat_id(self, chat_id: int):
        """Set the admin Telegram chat ID."""
        self._admin_chat_id = chat_id
        self.logger.info(f"Admin chat ID set: {chat_id}")
    
    def register_sender(self, sender: callable):
        """Register the Telegram sender function."""
        self._sender = sender
    
    def enable(self):
        """Enable admin alerts."""
        self._enabled = True
        self._start_processor()
    
    def disable(self):
        """Disable admin alerts."""
        self._enabled = False
        self._running = False
    
    def _start_processor(self):
        """Start the alert processor thread."""
        if self._running:
            return
        
        self._running = True
        self._alert_thread = threading.Thread(target=self._process_alerts, daemon=True)
        self._alert_thread.start()
    
    def _process_alerts(self):
        """Process alerts from queue."""
        while self._running and self._enabled:
            try:
                alert = self._alert_queue.get(timeout=1)
                self._send_alert(alert)
            except Exception:
                continue
    
    def _send_alert(self, alert: AdminAlert):
        """Send alert to Telegram admin."""
        if not self._enabled:
            return
        
        if not self._sender or not self._admin_chat_id:
            self.logger.warning("Cannot send alert: sender or admin chat ID not set")
            return
        
        try:
            # Format alert message
            formatted = self._format_alert(alert)
            
            # Send to Telegram admin only
            self._sender(chat_id=self._admin_chat_id, text=formatted)
            
            alert.sent = True
            self._alert_history.append(alert)
            
            self.logger.info(f"Admin alert sent: {alert.alert_type.value} - {alert.title}")
            
        except Exception as e:
            self.logger.error(f"Failed to send admin alert: {e}")
    
    def _format_alert(self, alert: AdminAlert) -> str:
        """Format alert message for Telegram."""
        emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨"
        }
        
        type_emoji = {
            AlertType.SERVER_STATUS: "🖥️",
            AlertType.DEPLOYMENT: "🚀",
            AlertType.API_FAILURE: "🔌",
            AlertType.PROVIDER_OUTAGE: "☁️",
            AlertType.HIGH_USAGE: "📊",
            AlertType.HIGH_COST: "💰",
            AlertType.CRITICAL_ERROR: "💥",
            AlertType.SYSTEM_WARNING: "⚙️"
        }
        
        msg = f"{emoji.get(alert.level, '📢')} *{alert.title}*\n\n"
        msg += f"{type_emoji.get(alert.alert_type, '📢')} {alert.message}\n\n"
        
        if alert.details:
            msg += "*Details:*\n"
            for key, value in alert.details.items():
                msg += f"• {key}: `{value}`\n"
        
        msg += f"\n🕐 {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        
        return msg
    
    def send_alert(self, level: AlertLevel, alert_type: AlertType, 
                   title: str, message: str, details: Optional[Dict] = None):
        """Queue an alert to be sent."""
        if not self._enabled:
            return
        
        alert = AdminAlert(
            level=level,
            alert_type=alert_type,
            title=title,
            message=message,
            details=details
        )
        
        self._alert_queue.put(alert)
        self.logger.debug(f"Alert queued: {alert_type.value} - {title}")
    
    # Convenience methods for common alerts
    
    def alert_server_status(self, status: str, details: Optional[Dict] = None):
        """Send server status alert."""
        self.send_alert(
            AlertLevel.INFO,
            AlertType.SERVER_STATUS,
            "Server Status Update",
            status,
            details
        )
    
    def alert_deployment(self, action: str, success: bool, details: Optional[Dict] = None):
        """Send deployment alert."""
        self.send_alert(
            AlertLevel.INFO if success else AlertLevel.ERROR,
            AlertType.DEPLOYMENT,
            "Deployment" if success else "Deployment Failed",
            action,
            details
        )
    
    def alert_api_failure(self, provider: str, error: str, details: Optional[Dict] = None):
        """Send API failure alert."""
        self.send_alert(
            AlertLevel.ERROR,
            AlertType.API_FAILURE,
            f"API Failure: {provider}",
            error,
            details
        )
    
    def alert_provider_outage(self, provider: str, is_down: bool, details: Optional[Dict] = None):
        """Send provider outage alert."""
        self.send_alert(
            AlertLevel.CRITICAL if is_down else AlertLevel.INFO,
            AlertType.PROVIDER_OUTAGE,
            f"{provider} {'DOWN' if is_down else 'Recovered'}",
            "Provider is not responding" if is_down else "Provider is back online",
            details
        )
    
    def alert_high_usage(self, metric: str, value: float, threshold: float, details: Optional[Dict] = None):
        """Send high usage alert."""
        self.send_alert(
            AlertLevel.WARNING,
            AlertType.HIGH_USAGE,
            "High Usage Detected",
            f"{metric}: {value:.1f} (threshold: {threshold})",
            details
        )
    
    def alert_high_cost(self, provider: str, cost: float, budget: float, details: Optional[Dict] = None):
        """Send high cost alert."""
        self.send_alert(
            AlertLevel.WARNING,
            AlertType.HIGH_COST,
            "High API Cost",
            f"{provider}: ${cost:.2f} (budget: ${budget:.2f})",
            details
        )
    
    def alert_critical_error(self, error: str, details: Optional[Dict] = None):
        """Send critical error alert."""
        self.send_alert(
            AlertLevel.CRITICAL,
            AlertType.CRITICAL_ERROR,
            "Critical System Error",
            error,
            details
        )
    
    def get_alert_history(self, limit: int = 50) -> List[Dict]:
        """Get alert history."""
        history = []
        for alert in self._alert_history[-limit:]:
            history.append({
                "level": alert.level.value,
                "type": alert.alert_type.value,
                "title": alert.title,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "sent": alert.sent
            })
        return history


# Singleton
_admin_alerts: Optional[AdminAlertManager] = None


def get_admin_alerts() -> AdminAlertManager:
    """Get admin alerts singleton."""
    global _admin_alerts
    if _admin_alerts is None:
        _admin_alerts = AdminAlertManager()
    return _admin_alerts