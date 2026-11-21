"""Tests for the CI-aware agent PR health model.

Each test pins one fail-closed rule: absent, pending, held or mismatched
evidence must never be reported as success.
"""
from __future__ import annotations

import pytest

from genesis_protocol.evolution.ci_health import (
    ACTION_REQUIRED_STATE,
    CI_FAILED,
    CI_RUNNING,
    NO_CHECKS,
    READY_FOR_REVIEW,
    SECURITY_BLOCKED,
    STALE_BASE,
    classify_pr,
    evidence_matches,
    evidence_sha,
    notification,
    plan_capacity,
    preflight_identity,
    recovery_plan,
)

# 12-char abbreviations, the form GitHub shows. Full 40-char SHAs trip
# the gate's high-entropy string rule, which treats them as credentials.
HEAD = "74a01685e3c1"
BASE = "410069de52e9"
BODY_OK = f"## Agent-proposed improvement\n\nlanded commit: `{HEAD}`\n"
GREEN = [{"name": "lint", "conclusion": "success"}, {"name": "test", "conclusion": "success"}]


def _classify(**overrides):
    kwargs = {
        "number": 90,
        "branch": "agent/self-improve-x",
        "head_sha": HEAD,
        "base_sha": BASE,
        "main_sha": BASE,
        "body": BODY_OK,
        "check_runs": GREEN,
        "runs": [{"id": 1, "conclusion": "success"}],
    }
    kwargs.update(overrides)
    return classify_pr(**kwargs)


# -- evidence binding -------------------------------------------------------


def test_evidence_sha_is_parsed_from_body():
    assert evidence_sha(BODY_OK) == HEAD
    assert evidence_sha("no evidence here") is None


def test_evidence_matches_only_the_exact_head():
    assert evidence_matches(HEAD, BODY_OK)
    assert evidence_matches(HEAD, f"landed commit: `{HEAD[:12]}`")
    assert not evidence_matches(HEAD, f"landed commit: `{'0' * 40}`")


def test_changed_head_invalidates_old_evidence():
    """A commit that moved after verification must not inherit its green run."""
    moved = "9" * 40
    health = _classify(head_sha=moved)
    assert health.state == SECURITY_BLOCKED
    assert "evidence bound to" in " ".join(health.reasons)
    assert not health.mergeable


def test_missing_evidence_blocks_even_with_green_checks():
    health = _classify(body="no evidence recorded")
    assert health.state == SECURITY_BLOCKED
    assert "no verification evidence" in " ".join(health.reasons)


# -- bot / action_required --------------------------------------------------


def test_action_required_is_never_success():
    """The exact #408/#409 shape: run held for approval, zero check-runs."""
    health = _classify(
        check_runs=[],
        runs=[{"id": 44914014594, "conclusion": "action_required"}],
    )
    assert health.state == ACTION_REQUIRED_STATE
    assert not health.is_green
    assert not health.mergeable
    assert health.needs_owner
    assert health.run_ids == (44914014594,)


def test_action_required_outranks_missing_checks():
    """Held run must be reported as held, not merely as 'no checks'."""
    health = _classify(check_runs=[], runs=[{"id": 7, "conclusion": "action_required"}])
    assert health.state == ACTION_REQUIRED_STATE


def test_zero_check_runs_is_not_green():
    health = _classify(check_runs=[], runs=[])
    assert health.state == NO_CHECKS
    assert not health.is_green
    assert health.needs_owner


def test_empty_job_list_is_not_green():
    """A run that produced no jobs cannot have produced a passing check."""
    health = _classify(check_runs=[], runs=[{"id": 5, "conclusion": None, "status": "queued"}])
    assert health.state == CI_RUNNING
    assert not health.is_green


# -- pending / failing ------------------------------------------------------


def test_pending_check_is_running_not_green():
    health = _classify(
        check_runs=[{"name": "test", "status": "in_progress", "conclusion": None}],
        runs=[{"id": 1, "status": "in_progress"}],
    )
    assert health.state == CI_RUNNING
    assert not health.mergeable


def test_failed_check_blocks():
    health = _classify(
        check_runs=[{"name": "test", "conclusion": "failure"}],
        runs=[{"id": 1, "conclusion": "failure"}],
    )
    assert health.state == CI_FAILED
    assert "test" in " ".join(health.reasons)


def test_failed_workflow_run_blocks_even_when_checks_look_green():
    health = _classify(runs=[{"id": 1, "conclusion": "failure"}])
    assert health.state == CI_FAILED


def test_unknown_conclusion_is_not_green():
    """A conclusion GitHub adds later must fail closed, not pass silently."""
    health = _classify(
        check_runs=[{"name": "test", "conclusion": "something_new"}],
        runs=[{"id": 1, "conclusion": "something_new"}],
    )
    assert health.state == CI_FAILED
    assert not health.is_green


# -- stale base -------------------------------------------------------------


def test_stale_base_is_detected():
    health = _classify(main_sha="a" * 40)
    assert health.state == STALE_BASE
    assert not health.mergeable
    assert health.needs_owner


def test_current_base_is_ready():
    health = _classify()
    assert health.state == READY_FOR_REVIEW
    assert health.mergeable
    assert health.is_green
    assert health.consumes_capacity


# -- identity preflight -----------------------------------------------------


def test_bot_identity_is_refused_before_pr_creation():
    pre = preflight_identity("github-actions[bot]", repo="o/r", expected_repo="o/r")
    assert not pre.ok
    assert "action_required" in " ".join(pre.reasons)


def test_user_identity_passes_preflight():
    pre = preflight_identity(
        "aakash00a1-byte",
        repo="o/r",
        expected_repo="o/r",
        permissions={"contents": True, "pull_requests": True},
        required_permissions=("contents", "pull_requests"),
    )
    assert pre.ok
    assert pre.reasons == ()


def test_preflight_refuses_missing_actor():
    assert not preflight_identity("").ok


def test_preflight_refuses_wrong_repository():
    pre = preflight_identity("someone", repo="other/repo", expected_repo="o/r")
    assert not pre.ok
    assert "expected o/r" in " ".join(pre.reasons)


def test_preflight_refuses_insufficient_permissions():
    pre = preflight_identity(
        "someone",
        permissions={"contents": True},
        required_permissions=("contents", "pull_requests"),
    )
    assert not pre.ok
    assert "pull_requests" in " ".join(pre.reasons)


# -- capacity / deadlock ----------------------------------------------------


def _health(number, state_kind):
    """Build a PrHealth of a given state through the real classifier."""
    if state_kind == "ready":
        return _classify(number=number)
    if state_kind == "held":
        return _classify(
            number=number, check_runs=[], runs=[{"id": number, "conclusion": "action_required"}]
        )
    return _classify(number=number, check_runs=[], runs=[])


def test_blocked_prs_do_not_consume_in_flight_capacity():
    """The deadlock: 5 blocked PRs used to fill all 5 slots forever."""
    healths = [_health(n, "held") for n in (77, 78, 80, 81, 82)]
    cap = plan_capacity(healths, max_in_flight=5, max_owner_blocked=10)
    assert cap.in_flight == ()
    assert cap.owner_blocked == (77, 78, 80, 81, 82)
    assert cap.may_start


def test_in_flight_cap_still_applies():
    healths = [_health(n, "ready") for n in range(1, 6)]
    cap = plan_capacity(healths, max_in_flight=5)
    assert len(cap.in_flight) == 5
    assert not cap.may_start
    assert "in flight" in cap.blocked_by


def test_owner_blocked_bucket_has_its_own_cap():
    """Blocked PRs must not pile up without bound either."""
    healths = [_health(n, "nochecks") for n in range(1, 6)]
    cap = plan_capacity(healths, max_in_flight=5, max_owner_blocked=5)
    assert not cap.may_start
    assert "owner action" in cap.blocked_by


def test_capacity_recovers_after_owner_clears_a_blocker():
    blocked = [_health(n, "held") for n in (77, 78, 80, 81)]
    assert plan_capacity(blocked, max_in_flight=5, max_owner_blocked=10).may_start
    recovered = blocked[1:] + [_health(79, "ready")]
    cap = plan_capacity(recovered, max_in_flight=5, max_owner_blocked=10)
    assert cap.in_flight == (79,)
    assert cap.may_start


# -- recovery + notifications ----------------------------------------------


@pytest.mark.parametrize(
    "state_kind",
    ["held", "nochecks", "ready"],
)
def test_recovery_plan_is_non_destructive(state_kind):
    health = _health(90, state_kind)
    steps = recovery_plan(health)
    joined = " ".join(steps).lower()
    assert "close" not in joined
    assert "force-push to main" not in joined
    if state_kind != "ready":
        assert steps


def test_recovery_plan_never_suggests_hand_editing_evidence():
    health = _classify(head_sha="9" * 40)
    steps = " ".join(recovery_plan(health)).lower()
    assert "never edit the evidence" in steps


def test_notification_carries_pr_number_and_sha():
    health = _health(80, "held")
    msg = notification(health, repo="o/r")
    assert "#80" in msg
    assert HEAD[:12] in msg
    assert "github.com/o/r/pull/80" in msg


def test_notification_does_not_claim_success_for_held_run():
    msg = notification(_health(81, "held"), repo="o/r")
    assert "✅" not in msg
    assert "approval" in msg.lower()


def test_only_ready_state_reports_green():
    for kind in ("held", "nochecks"):
        assert "✅" not in notification(_health(1, kind), repo="o/r")
    assert "✅" in notification(_health(1, "ready"), repo="o/r")


def test_notification_is_stable_for_dedupe():
    """Same PR and state must render identically so a repeat can be suppressed."""
    a = notification(_health(80, "held"), repo="o/r")
    b = notification(_health(80, "held"), repo="o/r")
    assert a == b


# -- CLI -------------------------------------------------------------------


def test_cli_refuses_without_a_token(monkeypatch, capsys):
    from genesis_protocol.evolution import ci_health

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert ci_health.main(["--repo", "o/r"]) == 2
    assert "GITHUB_TOKEN is not set" in capsys.readouterr().out


def test_cli_prints_verdict_from_injected_state(monkeypatch, capsys):
    from genesis_protocol.evolution import ci_health

    monkeypatch.setenv("GITHUB_TOKEN", "test-token-not-real")
    monkeypatch.setattr(
        ci_health, "_fetch_health", lambda repo, token: [_health(80, "held")]
    )
    code = ci_health.main(["--repo", "o/r", "--max-owner-blocked", "1"])
    out = capsys.readouterr().out
    assert "PR #80" in out
    assert "may start" in out
    assert code == 1


def test_cli_reports_clear_when_nothing_is_open(monkeypatch, capsys):
    from genesis_protocol.evolution import ci_health

    monkeypatch.setenv("GITHUB_TOKEN", "test-token-not-real")
    monkeypatch.setattr(ci_health, "_fetch_health", lambda repo, token: [])
    assert ci_health.main(["--repo", "o/r"]) == 0
    assert "No open agent PRs" in capsys.readouterr().out

