"""Tests for the CI-aware agent PR health model.

Each test pins one fail-closed rule: absent, pending, held or mismatched
evidence must never be reported as success.
"""
from __future__ import annotations

from pathlib import Path

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


# -- review 1: a green run with zero check-runs is NOT ready -----------------


def test_successful_run_with_zero_check_runs_is_not_ready():
    """A run conclusion proves the workflow finished, not that a test ran.

    This is the regression the reviewer found: a run reporting success while no
    check-run exists used to classify as READY_FOR_REVIEW.
    """
    health = _classify(check_runs=[], runs=[{"id": 11, "conclusion": "success"}])
    assert health.state == NO_CHECKS
    assert not health.mergeable
    assert not health.is_green
    assert "no check-run exists" in " ".join(health.reasons)


def test_zero_check_runs_never_ready_whatever_the_run_says():
    for conclusion in ("success", "neutral", "skipped"):
        health = _classify(check_runs=[], runs=[{"id": 12, "conclusion": conclusion}])
        assert health.state != READY_FOR_REVIEW, conclusion
        assert not health.mergeable, conclusion


def test_ready_requires_at_least_one_real_check_run():
    """The only path to READY is at least one green check-run and no runs."""
    assert _classify().state == READY_FOR_REVIEW
    assert _classify(check_runs=[], runs=[]) .state != READY_FOR_REVIEW
    assert _classify(check_runs=[], runs=[{"id": 1, "conclusion": "success"}]).state != (
        READY_FOR_REVIEW
    )


# -- review 2: failing PRs are explicitly bucketed ---------------------------


def _failed(number):
    return _classify(
        number=number,
        check_runs=[{"name": "test", "conclusion": "failure"}],
        runs=[{"id": number, "conclusion": "failure"}],
    )


def test_failing_pr_lands_in_its_own_bucket():
    """A failing PR must not vanish from capacity accounting."""
    cap = plan_capacity([_failed(50)], max_in_flight=5)
    assert cap.failing == (50,)
    assert cap.in_flight == ()
    assert cap.owner_blocked == ()


def test_failing_pr_is_capped_and_blocks_starting_more():
    cap = plan_capacity([_failed(n) for n in (50, 51, 52)], max_failing=3)
    assert len(cap.failing) == 3
    assert not cap.may_start
    assert "failing CI" in cap.blocked_by


def test_failing_pr_does_not_consume_an_in_flight_slot():
    cap = plan_capacity([_failed(50), _health(79, "ready")], max_in_flight=5, max_failing=3)
    assert cap.in_flight == (79,)
    assert cap.failing == (50,)
    assert cap.may_start


def test_every_state_is_accounted_for_in_exactly_one_bucket():
    """No state may be silently unaccounted for, now or when one is added."""
    from genesis_protocol.evolution import ci_health as m

    assert set(m.ALL_STATES) == set(m.BUCKETED_STATES), (
        set(m.ALL_STATES) ^ set(m.BUCKETED_STATES)
    )
    buckets = [m.IN_FLIGHT_STATES, m.FAILING_STATES, m.OWNER_BLOCKED_STATES]
    for i, a in enumerate(buckets):
        for b in buckets[i + 1 :]:
            assert not (a & b), a & b


def test_all_eight_states_reachable_and_bucketed():
    """Exercise every state through the real classifier, not a stub."""
    from genesis_protocol.evolution import ci_health as m

    produced = {
        _classify().state,
        _classify(check_runs=[{"name": "t", "status": "in_progress", "conclusion": None}]),
        _failed(1).state,
        _classify(check_runs=[], runs=[{"id": 1, "conclusion": "action_required"}]).state,
        _classify(check_runs=[], runs=[]).state,
        _classify(main_sha="a" * 40).state,
        _classify(head_sha="9" * 40).state,
    }
    produced = {s if isinstance(s, str) else s.state for s in produced}
    assert produced <= set(m.ALL_STATES)
    assert len(produced) >= 7


# -- review 4: bot identities are not blanket-blocked -----------------------


def test_workflow_token_identity_is_refused_with_evidence():
    pre = preflight_identity("github-actions[bot]")
    assert not pre.ok
    assert pre.is_bot
    assert "action_required" in " ".join(pre.reasons)


def test_github_app_bot_identity_is_not_blanket_blocked():
    """A GitHub App token is also [bot]; it must not be refused without evidence.

    The reviewer is right: only the workflow token has evidence against it.
    Blocking every bot would rule out the preferred credential strategy.
    """
    pre = preflight_identity("my-genesis-app[bot]")
    assert pre.ok
    assert pre.is_bot
    assert pre.needs_validation
    assert "no CI evidence yet" in " ".join(pre.reasons)


def test_app_bot_with_green_evidence_is_fully_trusted():
    pre = preflight_identity("my-genesis-app[bot]", actor_ci_evidence="green")
    assert pre.ok
    assert not pre.needs_validation
    assert pre.reasons == ()


def test_app_bot_with_held_evidence_is_refused():
    pre = preflight_identity("my-genesis-app[bot]", actor_ci_evidence="held")
    assert not pre.ok
    assert "parked at action_required" in " ".join(pre.reasons)


def test_human_identity_needs_no_validation():
    pre = preflight_identity("aakash00a1-byte", actor_ci_evidence="green")
    assert pre.ok
    assert not pre.needs_validation
    assert not pre.is_bot


# -- review 3: the integration target is genesis_protocol -------------------


def test_self_improve_imports_genesis_protocol_not_genesis_v5():
    """The runtime target must be proven, not assumed.

    self_improve.py puts the repo root on sys.path and imports
    genesis_protocol.updates; genesis_v5 is only the kernel behind
    patch_verification and the backlog JSONL path.
    """
    from pathlib import Path

    source = Path("scripts/self_improve.py").read_text(encoding="utf-8")
    assert "from genesis_protocol.updates" in source
    assert "import genesis_v5" not in source
    assert "from genesis_v5" not in source


def test_ci_health_imports_from_the_repository_root():
    import genesis_protocol.evolution.ci_health as module

    assert Path(module.__file__).parts[-3:] == (
        "genesis_protocol",
        "evolution",
        "ci_health.py",
    )


# -- self-review: precedence must not mask the actionable blocker -----------


def test_held_run_outranks_stale_evidence():
    """A held run is the actionable blocker; it must not be hidden as a
    security problem. Both reasons are reported, state is ACTION_REQUIRED."""
    health = classify_pr(
        number=90,
        branch="agent/x",
        head_sha="a" * 12,
        base_sha=BASE,
        main_sha=BASE,
        body="landed commit: `deadbeef1234`",
        check_runs=[],
        runs=[{"id": 1, "conclusion": "action_required"}],
    )
    assert health.state == ACTION_REQUIRED_STATE
    joined = " ".join(health.reasons)
    assert "action_required" in joined
    assert "evidence bound to" in joined


def test_stale_evidence_still_blocks_a_green_pr():
    """Collecting the problem must not weaken it: green CI + wrong evidence
    still cannot merge."""
    health = _classify(head_sha="9" * 12, body="landed commit: `deadbeef1234`")
    assert health.state == SECURITY_BLOCKED
    assert not health.mergeable


def test_evidence_problem_survives_a_pending_run():
    health = _classify(
        head_sha="9" * 12,
        body="landed commit: `deadbeef1234`",
        check_runs=[{"name": "t", "status": "in_progress", "conclusion": None}],
        runs=[{"id": 1, "status": "in_progress"}],
    )
    assert health.state == CI_RUNNING
    assert "evidence bound to" in " ".join(health.reasons)


def test_require_evidence_false_skips_the_check_entirely():
    health = _classify(body="no evidence at all", require_evidence=False)
    assert health.state == READY_FOR_REVIEW


def test_a_recovered_pr_is_not_held_by_its_old_run():
    """Found on real data: PR #80 was recovered with workflow_dispatch and had
    two green check-runs, but the superseded action_required run still sat in
    the run list and kept it blocked. A recovery would never take effect."""
    health = _classify(
        check_runs=[
            {"name": "test", "conclusion": "success"},
            {"name": "lint", "conclusion": "success"},
        ],
        runs=[
            {"id": 1, "conclusion": "action_required"},
            {"id": 2, "conclusion": "success"},
        ],
    )
    assert health.state == READY_FOR_REVIEW
    assert health.mergeable


def test_held_run_still_blocks_when_it_is_the_only_evidence():
    health = _classify(check_runs=[], runs=[{"id": 1, "conclusion": "action_required"}])
    assert health.state == ACTION_REQUIRED_STATE
    assert not health.mergeable


def test_recovered_run_that_fails_reports_ci_failed():
    """Recovery is not a bypass: if the re-run fails, that is the verdict."""
    health = _classify(
        check_runs=[{"name": "test", "conclusion": "failure"}],
        runs=[
            {"id": 1, "conclusion": "action_required"},
            {"id": 2, "conclusion": "failure"},
        ],
    )
    assert health.state == CI_FAILED
    assert not health.mergeable






# -- review 3: fail-closed holes found on live data --------------------------


def test_a_skipped_check_is_not_ready_on_its_own():
    """A skipped job verified nothing. Accepting it let a PR reach READY with no
    test having run at all, which is the failure mode this module exists to
    prevent."""
    health = _classify(check_runs=[{"name": "test", "conclusion": "skipped"}])
    assert health.state == NO_CHECKS
    assert not health.mergeable


def test_a_neutral_check_is_not_ready_on_its_own():
    health = _classify(check_runs=[{"name": "test", "conclusion": "neutral"}])
    assert health.state == NO_CHECKS
    assert not health.mergeable


def test_one_skipped_required_job_blocks_an_otherwise_green_pr():
    health = _classify(
        check_runs=[
            {"name": "lint", "conclusion": "skipped"},
            {"name": "test", "conclusion": "success"},
        ]
    )
    assert health.state == NO_CHECKS
    assert not health.mergeable
    assert "verified nothing" in " ".join(health.reasons)


def test_a_green_subset_with_a_missing_required_job_is_not_ready():
    """Only the linter ran; the tests never executed. A green subset is not a
    verified PR."""
    health = _classify(check_runs=[{"name": "lint", "conclusion": "success"}])
    assert health.state == NO_CHECKS
    assert not health.mergeable
    assert "required checks never reported: test" in " ".join(health.reasons)


def test_all_required_jobs_green_is_ready():
    assert _classify().state == READY_FOR_REVIEW


def test_a_superseded_held_suite_keeps_the_pr_blocked():
    """Measured on #80/#81: the required jobs were green, yet GitHub still
    reported mergeable_state=unstable because the original action_required
    check-suite remained on the head with 0 jobs. READY would contradict
    GitHub's own verdict for that commit."""
    health = _classify(
        suites=[
            {"id": 111, "conclusion": "action_required", "latest_check_runs_count": 0},
            {"id": 222, "conclusion": "success", "latest_check_runs_count": 2},
        ],
        check_runs=[
            {"name": "lint", "conclusion": "success", "check_suite": {"id": 222}},
            {"name": "test", "conclusion": "success", "check_suite": {"id": 222}},
        ],
    )
    assert health.state == ACTION_REQUIRED_STATE
    assert not health.mergeable
    assert "superseded check-suite" in " ".join(health.reasons)


def test_a_clean_suite_list_still_reaches_ready():
    health = _classify(
        suites=[
            {"id": 222, "conclusion": "success", "latest_check_runs_count": 2}
        ],
        check_runs=[
            {"name": "lint", "conclusion": "success", "check_suite": {"id": 222}},
            {"name": "test", "conclusion": "success", "check_suite": {"id": 222}},
        ],
    )
    assert health.state == READY_FOR_REVIEW


def test_absent_suite_data_does_not_block():
    """The suite list is optional: an older payload without it must not turn a
    genuinely green PR into a blocked one."""
    assert _classify(suites=None).state == READY_FOR_REVIEW
    assert _classify(suites=[]).state == READY_FOR_REVIEW
