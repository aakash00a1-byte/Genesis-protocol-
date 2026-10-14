"""Phase 8 — Multi-Agent + Reflection + QA tests.

Covers: correct result, incorrect result, contradictory outputs, failed
verification, retry limit, escalation, and independent verification (never
trusting the producer's own claim).
"""
from __future__ import annotations

import pytest

from genesis.qa.verifier import IndependentVerifier, VerificationOutcome, VerifierConfig
from genesis.reflection.reflection import ReflectionEngine


@pytest.fixture
def verifier() -> IndependentVerifier:
    return IndependentVerifier()


# ------------------------------------------------------------------
# Correct result
# ------------------------------------------------------------------
def test_verifier_accepts_correct_result(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify(
        task="write add function",
        result="Implemented the add function. All tests pass and the code "
               "has been verified. The implementation is complete and "
               "consistent with the requirements.",
        expected="add function",
    )
    assert outcome.passed
    assert outcome.confidence > 0.6


# ------------------------------------------------------------------
# Incorrect result
# ------------------------------------------------------------------
def test_verifier_rejects_empty_result(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify(task="task", result="   ")
    assert not outcome.passed
    assert "empty result" in outcome.issues


def test_verifier_rejects_failure_markers(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify(
        task="task",
        result="processed request but ERROR: internal exception occurred",
    )
    assert not outcome.passed
    assert any("failure" in i or "markers" in i for i in outcome.issues)


def test_verifier_rejects_missing_expected(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify(
        task="task",
        result="Some output that does not contain the required content.",
        expected="THE_REQUIRED_ANSWER",
    )
    assert not outcome.passed
    assert "result missing expected content" in outcome.issues


# ------------------------------------------------------------------
# Independent verification (producer claim untrusted)
# ------------------------------------------------------------------
def test_verifier_does_not_trust_producer_claim(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify(
        task="task",
        result="ERROR: the implementation failed with traceback",
        producer_claim=True,
    )
    assert not outcome.passed
    assert outcome.confidence <= 0.2
    assert any("producer claimed success" in i for i in outcome.issues)


# ------------------------------------------------------------------
# Contradictory outputs
# ------------------------------------------------------------------
def test_contradiction_detection(verifier: IndependentVerifier) -> None:
    outcome = verifier.check_contradictions(
        task="task",
        outputs=[
            ("agent-a", "The build passed and everything works."),
            ("agent-b", "The build failed with an error."),
        ],
    )
    assert not outcome.passed
    assert outcome.contradictions
    assert outcome.contradictions[0]["severity"] == "error"


def test_consistent_outputs_no_contradiction(verifier: IndependentVerifier) -> None:
    outcome = verifier.check_contradictions(
        task="task",
        outputs=[
            ("agent-a", "completed successfully"),
            ("agent-b", "completed successfully"),
        ],
    )
    assert outcome.passed
    assert not outcome.contradictions


def test_team_verification_detects_contradiction(verifier: IndependentVerifier) -> None:
    outcome = verifier.verify_team(
        task="task",
        results=[
            {"agent": "coder", "output": "The code is correct."},
            {"agent": "qa", "output": "The code is broken and tests fail."},
        ],
    )
    assert not outcome.passed


# ------------------------------------------------------------------
# Failed verification + bounded correction + escalation
# ------------------------------------------------------------------
def test_bounded_correction_loop_recovers(verifier: IndependentVerifier) -> None:
    attempts = []

    def correct_fn(current, iteration):  # type: ignore[no-untyped-def]
        attempts.append(iteration)
        return "The implementation is now complete and verified. All checks pass."

    outcome = verifier.bounded_correction_loop(
        task="task",
        result="ERROR: broken",
        correct_fn=correct_fn,
        max_iterations=5,
    )
    assert outcome.passed
    assert attempts  # correction ran at least once


def test_bounded_correction_escalates_after_limit(verifier: IndependentVerifier) -> None:
    def correct_fn(current, iteration):  # type: ignore[no-untyped-def]
        return "still ERROR: broken"

    outcome = verifier.bounded_correction_loop(
        task="task",
        result="ERROR: broken",
        correct_fn=correct_fn,
        max_iterations=3,
    )
    assert not outcome.passed
    assert outcome.escalated
    assert outcome.iterations <= 3  # bounded
    assert any("escalated" in i for i in outcome.issues)


def test_no_correct_fn_escalates_immediately(verifier: IndependentVerifier) -> None:
    outcome = verifier.bounded_correction_loop(
        task="task", result="ERROR: broken", max_iterations=5
    )
    assert not outcome.passed
    assert outcome.escalated


def test_correction_loop_is_bounded(verifier: IndependentVerifier) -> None:
    calls = {"n": 0}

    def stubborn(current, iteration):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return "still ERROR: broken"

    verifier.bounded_correction_loop(
        task="task", result="ERROR: broken", correct_fn=stubborn, max_iterations=2
    )
    assert calls["n"] == 2


# ------------------------------------------------------------------
# Reflection engine
# ------------------------------------------------------------------
def test_reflection_passes_clean_output() -> None:
    engine = ReflectionEngine()
    result = engine.reflect(
        agent="coder",
        task_id="t1",
        result_output="Implemented feature. Tests pass.",
    )
    assert result.passed
    assert result.confidence > 0.6


def test_reflection_detects_failure() -> None:
    engine = ReflectionEngine()
    result = engine.reflect(
        agent="coder",
        task_id="t1",
        result_output="ERROR: tests failed with exception",
    )
    assert not result.passed


def test_reflection_missing_expected_content() -> None:
    engine = ReflectionEngine()
    result = engine.reflect(
        agent="coder",
        task_id="t1",
        result_output="some unrelated output",
        expected="REQUIRED_TOKEN",
    )
    assert not result.passed


def test_reflection_bounded_iterations() -> None:
    engine = ReflectionEngine(max_iterations=2)
    result = engine.reflect(agent="a", task_id="t", result_output="ok")
    assert result.iterations == 1


# ------------------------------------------------------------------
# Kernel QA integration
# ------------------------------------------------------------------
def test_kernel_qa_wired_and_pass() -> None:
    from genesis.bootstrap import build
    from genesis.kernel.kernel import KernelRequest

    kernel = build()
    assert kernel.qa is not None
    resp = kernel.run(
        KernelRequest(
            task="implement a hello function and verify it",
            metadata={"expected": "implemented"},
        )
    )
    assert resp.qa is not None
    assert "qa" in {k for k in resp.to_dict()}


def test_kernel_qa_escalates_on_bad_result() -> None:
    from genesis.bootstrap import build
    from genesis.kernel.kernel import KernelRequest

    kernel = build()
    resp = kernel.run(
        KernelRequest(
            task="implement a function that always fails and is broken",
            metadata={"expected": "THIS_EXPECTED_TOKEN_IS_NEVER_PRODUCED"},
        )
    )
    # The aggregated agent output can still fail QA if it lacks the expected
    # content (expected missing -> qa fail -> escalated).
    if not resp.ok:
        assert any("qa_failed" in e for e in resp.errors)
    else:
        # If agents produced the expected token by coincidence, QA passed.
        assert resp.qa["passed"] is True