"""Tests for resilient failure response: learn and continue, never blame."""
from __future__ import annotations

from genesis.resilience.policy import (
    FailureEvent,
    FailureKind,
    ResiliencePolicy,
)


def test_response_never_assigns_blame() -> None:
    policy = ResiliencePolicy()
    response = policy.respond(
        FailureEvent(component="tool", what="boom", kind=FailureKind.TRANSIENT)
    )
    assert response.attribute_blame is False
    assert policy.summary()["blame_assigned"] == 0


def test_transient_failure_advises_a_single_retry() -> None:
    policy = ResiliencePolicy(max_continuations=3)
    response = policy.respond(
        FailureEvent(component="provider", what="timeout", kind=FailureKind.TRANSIENT)
    )
    assert response.should_continue is True
    assert response.retry_advised is True
    assert response.lesson


def test_permanent_failure_continues_without_retrying() -> None:
    policy = ResiliencePolicy()
    response = policy.respond(
        FailureEvent(component="tool", what="bad input", kind=FailureKind.PERMANENT)
    )
    assert response.should_continue is False
    assert response.retry_advised is False


def test_continuations_are_bounded_so_it_never_spirals() -> None:
    policy = ResiliencePolicy(max_continuations=2)
    for _ in range(5):
        policy.respond(
            FailureEvent(component="x", what="flaky", kind=FailureKind.TRANSIENT)
        )
    summary = policy.summary()
    assert summary["continuations_used"] == 2
    assert summary["continuations_left"] == 0


def test_reset_starts_a_fresh_budget_without_a_grudge() -> None:
    policy = ResiliencePolicy(max_continuations=1)
    policy.respond(
        FailureEvent(component="x", what="flaky", kind=FailureKind.TRANSIENT)
    )
    policy.reset()
    response = policy.respond(
        FailureEvent(component="x", what="flaky", kind=FailureKind.TRANSIENT)
    )
    assert response.should_continue is True
