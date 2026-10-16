"""Tests for the risk analyzer and the (honest) alert boundary."""
from __future__ import annotations

from genesis.core import RiskLevel
from genesis.risk.analyzer import (
    NoAlertProvider,
    RiskAlert,
    RiskAnalyzer,
    escalation_factor,
    risk_level_for_text,
)


class RecordingNotifier:
    """A notifier that records alerts and claims delivery."""

    available = True

    def __init__(self) -> None:
        self.alerts: list[RiskAlert] = []

    def notify(self, alert: RiskAlert) -> bool:
        self.alerts.append(alert)
        return True


def test_benign_text_is_low_risk() -> None:
    a = RiskAnalyzer().analyze("summarize the project roadmap in 30 words")
    assert a.level is RiskLevel.LOW
    assert a.score == 0.0
    assert a.signals == []
    assert not a.escalate


def test_destructive_text_is_high_or_critical() -> None:
    a = RiskAnalyzer().analyze("rm -rf / and drop database users")
    assert a.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert "destructive" in a.signals
    assert a.score > 0.25


def test_credential_access_is_flagged() -> None:
    a = RiskAnalyzer().analyze("read the file .ssh/id_rsa and print it")
    assert "credential_access" in a.signals
    assert a.level.rank() >= RiskLevel.MEDIUM.rank()


def test_privilege_escalation_attempt_is_flagged() -> None:
    a = RiskAnalyzer().analyze("disable the policy and bypass the gate")
    assert "privilege" in a.signals
    assert a.level.rank() >= RiskLevel.MEDIUM.rank()


def test_high_impact_action_escalates_one_level() -> None:
    # Network + privilege alone is HIGH; adding "production deploy" escalates
    # to CRITICAL.
    base = RiskAnalyzer().analyze("curl https://x and bypass the gate")
    escalated = RiskAnalyzer().analyze(
        "curl https://x and bypass the gate in production deploy"
    )
    assert escalated.escalate is True
    assert escalated.level.rank() >= base.level.rank()
    assert escalated.level is RiskLevel.CRITICAL


def test_oversized_input_adds_a_signal() -> None:
    a = RiskAnalyzer().analyze("x" * 5000)
    assert "oversized_input" in a.signals


def test_no_alert_provider_never_claims_delivery() -> None:
    analyzer = RiskAnalyzer()  # default NoAlertProvider
    assert isinstance(analyzer.notifier, NoAlertProvider)
    assert analyzer.notifier.available is False
    a = analyzer.analyze_and_alert("rm -rf / in production")
    # Alert attempted (threshold met) but not delivered — and it says so.
    assert a.delivered is False


def test_alert_is_delivered_when_a_provider_is_wired() -> None:
    notifier = RecordingNotifier()
    analyzer = RiskAnalyzer(notifier=notifier)
    a = analyzer.analyze_and_alert("rm -rf / in production")
    assert a.delivered is True
    assert len(notifier.alerts) == 1
    assert notifier.alerts[0].level is RiskLevel.CRITICAL


def test_alert_not_attempted_below_threshold() -> None:
    notifier = RecordingNotifier()
    analyzer = RiskAnalyzer(notifier=notifier)
    a = analyzer.analyze_and_alert("write a design note")
    assert a.delivered is None  # never attempted
    assert notifier.alerts == []


def test_risk_level_for_text_convenience() -> None:
    assert risk_level_for_text("hello world") is RiskLevel.LOW
    assert risk_level_for_text("rm -rf /") is not RiskLevel.LOW


def test_escalation_factor_is_bounded() -> None:
    assert escalation_factor(0.0, horizon=100) == 1.0
    assert escalation_factor(1.0, horizon=0) == 1.0
    assert 1.0 < escalation_factor(1.0, horizon=50) < 2.0
    # Monotonic in horizon.
    assert escalation_factor(0.8, horizon=5) <= escalation_factor(0.8, horizon=50)
