"""The benchmark must be reproducible, and the checker must be able to say no."""

import pytest

from genesis_protocol.research import (
    CONTINGENT,
    CONTRADICTION,
    PROBLEMS,
    TAUTOLOGY,
    LeanChecker,
    Problem,
    TruthTableChecker,
    classify,
    run_benchmark,
)
from genesis_protocol.research.benchmark import LogicError, parse


def test_classify_tautology_contingent_contradiction():
    assert classify("a | !a")[0] == TAUTOLOGY
    assert classify("a -> b")[0] == CONTINGENT
    assert classify("a & !a")[0] == CONTRADICTION


def test_classify_returns_a_counterexample_for_a_non_tautology():
    kind, witness = classify("a -> b")
    assert kind == CONTINGENT
    assert witness == {"a": True, "b": False}


def test_the_parser_rejects_malformed_statements():
    for bad in ("", "a &", "(& a)", "a b", "a -> "):
        with pytest.raises(LogicError):
            parse(bad)


def test_precedence_matches_convention():
    # ! binds tighter than &, which binds tighter than |, which binds tighter than ->
    assert classify("a | b & c")[0] == CONTINGENT
    assert classify("!(a & b) <-> (!a | !b)")[0] == TAUTOLOGY
    assert classify("(a | b) & c")[0] == CONTINGENT


def test_the_benchmark_passes_and_the_checker_is_discriminating():
    report = run_benchmark()
    assert report.total == len(PROBLEMS)
    assert report.passed == report.total
    assert report.checker_discriminating is True
    assert report.available is True


def test_a_checker_that_accepts_everything_is_reported_broken():
    class YesMan:
        name = "yes_man"

        def check(self, statement, expected=TAUTOLOGY):
            from genesis_protocol.research.benchmark import CheckResult
            return CheckResult(True, "looks fine to me")

    report = run_benchmark(YesMan())
    assert report.passed == report.total          # it says yes to everything...
    assert report.checker_discriminating is False  # ...and that is the finding


def test_a_score_is_never_a_discovery():
    assert run_benchmark().to_dict()["is_discovery"] is False


def test_negative_controls_are_part_of_the_problem_set():
    controls = [p for p in PROBLEMS if p.id.startswith("control")]
    assert len(controls) >= 3
    assert all(p.expected != TAUTOLOGY for p in controls)


def test_lean_is_reported_unavailable_rather_than_faked():
    checker = LeanChecker(binary="/nonexistent/lean")
    assert checker.available is False
    result = checker.check("1 = 1")
    assert result.available is False
    assert result.passed is False
    assert "no Lean claim" in result.detail


def test_a_custom_problem_set_is_supported():
    report = run_benchmark(TruthTableChecker(), problems=[
        Problem("custom_ok", "a -> a", TAUTOLOGY),
        Problem("control_custom", "a -> b", CONTINGENT),
    ])
    assert report.passed == 2
    assert report.checker_discriminating is True


def test_lean_will_not_run_without_the_owner_even_when_installed():
    """The CLI gate is the only way a checker may start a process."""
    import sys

    checker = LeanChecker(binary=sys.executable)
    assert checker.available is True
    result = checker.check("1 = 1")          # no owner identity -> refused
    assert result.passed is False
    assert "CLI gate" in result.detail
