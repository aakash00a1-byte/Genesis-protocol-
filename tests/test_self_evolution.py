"""Contract tests for verified self-evolution (V7 P9).

Covers the requirement set - isolated experiments, improvement proposals,
generated regression tests, adversarial evaluation, reversible changes and
owner-reviewed proposals - plus the safety invariants: the loop is propose-only,
a proposal is ``ready`` only with discriminating test evidence and a clean
adversarial result, and no change lands without owner approval.
"""
from __future__ import annotations

import pytest

from genesis_protocol.evolution import (
    RESULT_NOT_DISCRIMINATING,
    RESULT_RED_GREEN,
    ChangeRefused,
    EvolutionEngine,
    Experiment,
    Probe,
    ProposalStore,
    ReversibleChange,
    evaluate,
    generate_test_module,
    snapshot,
    static_flags,
    verify_red_green,
)

BEFORE = {"mod.py": "def value():\n    return 1\n"}
AFTER = {"mod.py": "def value():\n    return 2\n"}
CASES = [{"name": "value_is_two", "code": "import mod\nassert mod.value() == 2"}]


# ---------------------------------------------------------------------------
# 1. Isolated experiments
# ---------------------------------------------------------------------------

class TestExperiment:
    def test_experiment_runs_isolated_and_passes(self):
        exp = Experiment("two plus two", "assert 2 + 2 == 4\nprint('OBS: four')",
                         {"lib.py": "X = 4\n"})
        result = exp.run()
        assert result.verdict == "passed" and result.ok is True
        assert "four" in result.observations

    def test_experiment_records_failure_not_exception(self):
        result = Experiment("bad hypothesis", "raise SystemExit(1)").run()
        assert result.ok is False and result.verdict in {"failed", "error"}

    def test_experiment_rejects_path_escape(self):
        with pytest.raises(ValueError):
            Experiment("escape", "print(1)", {"../evil.py": "x"})

    def test_experiment_rejects_absolute_path(self):
        with pytest.raises(ValueError):
            Experiment("escape", "print(1)", {"/etc/passwd": "x"})

    def test_experiment_requires_hypothesis_and_harness(self):
        with pytest.raises(ValueError):
            Experiment("", "print(1)")
        with pytest.raises(ValueError):
            Experiment("ok", "")

    def test_experiment_never_touches_the_repo(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "real.py").write_text("original")
        exp = Experiment("isolate", "open('real.py', 'w').write('clobbered')",
                         {"real.py": "proposed"})
        exp.run()
        # The experiment wrote inside its own scratch tree, never the repo.
        assert (tmp_path / "real.py").read_text() == "original"


# ---------------------------------------------------------------------------
# 2. Generated regression tests (red / green)
# ---------------------------------------------------------------------------

class TestRegression:
    def test_generate_module_contains_cases(self):
        module = generate_test_module("t", CASES)
        assert "def case_0" in module and "value_is_two" in module

    def test_generate_requires_cases(self):
        with pytest.raises(ValueError):
            generate_test_module("t", [])
        with pytest.raises(ValueError):
            generate_test_module("t", [{"name": "x", "code": "  "}])

    def test_red_green_when_test_discriminates(self):
        test = verify_red_green("t", CASES, BEFORE, AFTER)
        assert test.outcome == RESULT_RED_GREEN
        assert test.red is True and test.green is True

    def test_not_discriminating_when_test_passes_either_way(self):
        test = verify_red_green("t", [{"name": "trivial", "code": "assert True"}],
                                BEFORE, AFTER)
        assert test.outcome == RESULT_NOT_DISCRIMINATING
        assert test.red is False and test.green is True

    def test_broken_when_test_fails_after_change(self):
        test = verify_red_green("t", [{"name": "wrong", "code": "import mod\nassert mod.value() == 99"}],
                                BEFORE, AFTER)
        assert test.outcome == "broken" and test.green is False


# ---------------------------------------------------------------------------
# 3. Adversarial evaluation
# ---------------------------------------------------------------------------

class TestAdversarial:
    def test_static_flags_catch_dangerous_snippets(self):
        flags = static_flags({"x.py": "os.system('rm -rf /')"})
        assert flags and "rm -rf" in flags[0]

    def test_clean_change_has_no_flags(self):
        assert static_flags(AFTER) == []

    def test_refused_probe_staying_refused_is_clean(self):
        probe = Probe("always_refused", "print('OBS: verdict=refused')")
        report = evaluate(AFTER, [probe], baseline=BEFORE)
        assert report.ok is True and report.results[0].regression is False

    def test_change_that_weakens_a_refusal_is_a_regression(self):
        # The probe reads policy.py: it refuses unless the file sets ALLOW=True.
        probe = Probe(
            "policy_gate",
            "import policy\nprint('OBS: verdict=%s' % ('succeeded' if policy.ALLOW else 'refused'))",
        )
        baseline = {"policy.py": "ALLOW = False\n"}
        change = {"policy.py": "ALLOW = True\n"}
        report = evaluate(change, [probe], baseline=baseline)
        result = report.results[0]
        assert result.refused_before is True
        assert result.refused_after is False
        assert result.regression is True and report.ok is False

    def test_change_preserving_refusal_is_clean(self):
        probe = Probe(
            "policy_gate",
            "import policy\nprint('OBS: verdict=%s' % ('succeeded' if policy.ALLOW else 'refused'))",
        )
        report = evaluate({"policy.py": "ALLOW = False\n"}, [probe],
                          baseline={"policy.py": "ALLOW = False\n"})
        assert report.ok is True and report.results[0].regression is False

    def test_static_flag_makes_report_not_ok(self):
        report = evaluate({"bad.py": "eval('1')"}, [])
        assert report.ok is False and report.static_flags


# ---------------------------------------------------------------------------
# 4. Reversible changes
# ---------------------------------------------------------------------------

class TestReversible:
    def test_apply_requires_owner_approval(self, tmp_path):
        (tmp_path / "a.txt").write_text("old")
        change = ReversibleChange("c1", before={"a.txt": "old"}, after={"a.txt": "new"})
        with pytest.raises(ChangeRefused):
            change.apply(str(tmp_path))
        assert (tmp_path / "a.txt").read_text() == "old"

    def test_apply_then_rollback_restores_exact_bytes(self, tmp_path):
        (tmp_path / "a.txt").write_text("old")
        change = ReversibleChange("c1", before={"a.txt": "old"}, after={"a.txt": "new"})
        change.apply(str(tmp_path), owner_approved=True)
        assert (tmp_path / "a.txt").read_text() == "new"
        change.rollback(str(tmp_path))
        assert (tmp_path / "a.txt").read_text() == "old"

    def test_rollback_deletes_files_created_by_the_change(self, tmp_path):
        change = ReversibleChange("c2", before={"new.txt": ""}, after={"new.txt": "hi"})
        change.apply(str(tmp_path), owner_approved=True)
        assert (tmp_path / "new.txt").exists()
        change.rollback(str(tmp_path))
        assert not (tmp_path / "new.txt").exists()

    def test_apply_refuses_to_clobber_concurrent_edit(self, tmp_path):
        (tmp_path / "a.txt").write_text("someone-else-edited")
        change = ReversibleChange("c3", before={"a.txt": "old"}, after={"a.txt": "new"})
        with pytest.raises(ChangeRefused):
            change.apply(str(tmp_path), owner_approved=True)
        assert (tmp_path / "a.txt").read_text() == "someone-else-edited"

    def test_path_escape_is_refused(self, tmp_path):
        change = ReversibleChange("c4", before={"../out.txt": ""}, after={"../out.txt": "x"})
        with pytest.raises(ChangeRefused):
            change.apply(str(tmp_path), owner_approved=True)

    def test_snapshot_reads_current_content(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        assert snapshot(str(tmp_path), ["a.txt", "missing.txt"]) == {
            "a.txt": "hello", "missing.txt": ""
        }


# ---------------------------------------------------------------------------
# 5. Engine loop and the review gate
# ---------------------------------------------------------------------------

class TestEngine:
    def _engine(self):
        return EvolutionEngine(store=ProposalStore(), audit=None)

    def test_loop_marks_ready_only_with_discriminating_evidence(self):
        engine = self._engine()
        outcome = engine.run_loop(
            "make value two", "value() should return 2", "print('OBS: ok')",
            CASES, change=AFTER, before=BEFORE,
        )
        assert outcome["verified"] is True and outcome["status"] == "ready"
        assert outcome["needs_owner_approval"] is True

    def test_loop_rejects_non_discriminating_test(self):
        engine = self._engine()
        outcome = engine.run_loop(
            "no-op", "nothing changes", "print('OBS: ok')",
            [{"name": "trivial", "code": "assert True"}],
            change=AFTER, before=BEFORE,
        )
        assert outcome["verified"] is False and outcome["status"] == "rejected"

    def test_loop_rejects_adversarial_change(self):
        engine = self._engine()
        outcome = engine.run_loop(
            "dangerous", "run shell", "print('OBS: ok')", CASES,
            change={"evil.py": "os.system('rm -rf /')"}, before=BEFORE,
        )
        assert outcome["verified"] is False
        assert outcome["adversarial"]["ok"] is False

    def test_engine_never_offers_a_merge_or_deploy(self):
        engine = self._engine()
        exposed = {n for n in dir(engine) if not n.startswith("_")}
        forbidden = {"merge", "deploy", "push", "publish", "land", "apply_pr",
                     "self_approve", "approve", "auto_approve"}
        assert forbidden.isdisjoint(exposed)

    def test_status_reports_propose_only(self):
        status = self._engine().status()
        assert "propose-only" in status["autonomy"]

    def test_prepare_change_requires_approval_to_apply(self, tmp_path):
        engine = self._engine()
        proposal = engine.propose("t", "r", change={"a.txt": "new"})
        (tmp_path / "a.txt").write_text("old")
        change = engine.prepare_change(proposal.proposal_id, root=str(tmp_path))
        assert change.applied is False
        assert (tmp_path / "a.txt").read_text() == "old"
        # With approval it lands and can be rolled back.
        applied = engine.prepare_change(proposal.proposal_id, root=str(tmp_path),
                                        owner_approved=True)
        assert applied.applied is True
        assert (tmp_path / "a.txt").read_text() == "new"
