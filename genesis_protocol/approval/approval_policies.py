"""Approval Policies - Genesis Protocol v1.9"""

from enum import Enum


class ApprovalPolicy(Enum):
    STRICT = "strict"
    NORMAL = "normal"
    DEVELOPER = "developer"


_policy = ApprovalPolicy.NORMAL


def get_policy() -> ApprovalPolicy:
    return _policy


def set_policy(policy: ApprovalPolicy):
    global _policy
    _policy = policy


def requires_approval(risk_level: str) -> bool:
    return True  # Always require approval
