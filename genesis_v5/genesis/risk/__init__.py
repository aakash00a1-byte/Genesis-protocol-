"""Risk analysis layer.

Scores the risk of a task or failure and recommends a response. It never
executes anything; the Kernel remains the authority.
"""
from __future__ import annotations

from genesis.risk.analyzer import (
    AlertNotifier,
    NoAlertProvider,
    RiskAlert,
    RiskAnalyzer,
    RiskAssessment,
    escalation_factor,
    risk_level_for_text,
)

__all__ = [
    "AlertNotifier",
    "NoAlertProvider",
    "RiskAlert",
    "RiskAnalyzer",
    "RiskAssessment",
    "escalation_factor",
    "risk_level_for_text",
]
