"""Verified self-evolution engine (V7 P9).

One place that ties the P9 pieces into a *verifiable* loop, in the order that
keeps the system honest:

1. **experiment** - try the change in an isolated scratch tree (never the repo);
2. **propose**    - record it, with canonical risk assessment;
3. **prove**      - generate a regression test and require it to be red before /
                    green after;
4. **attack**     - run adversarial probes and require no regression;
5. **prepare**    - build a reversible change (with a full backup) ready to land;
6. **review**     - hand the result to a human. The engine never merges, never
                    deploys, never approves itself.

The engine reuses the canonical ``SecurityEventLog`` for its audit trail (source
``evolution``) and refuses to mark anything ``ready`` unless the regression test
discriminates *and* the adversarial evaluation is clean.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from genesis_protocol.evolution.adversarial import (
    AdversarialReport,
    Probe,
    default_probes,
    evaluate,
)
from genesis_protocol.evolution.experiment import Experiment, ExperimentResult
from genesis_protocol.evolution.proposals import (
    STATUS_EXPERIMENTING,
    STATUS_READY,
    STATUS_REJECTED,
    STATUS_VERIFIED,
    EvolutionProposal,
    ProposalStore,
)
from genesis_protocol.evolution.regression import (
    RESULT_RED_GREEN,
    RegressionTest,
    verify_red_green,
)
from genesis_protocol.evolution.reversible import ReversibleChange, snapshot


class EvolutionEngine:
    """Runs the verified self-evolution loop; proposes, never lands."""

    def __init__(
        self,
        store: Optional[ProposalStore] = None,
        audit: Optional[Any] = None,
        repo_root: Optional[str] = None,
    ):
        self.store = store or ProposalStore()
        self._audit = audit
        self.repo_root = repo_root or "."

    @property
    def audit(self) -> Any:
        if self._audit is None:
            try:
                from genesis_protocol.guardian.events import get_security_log

                self._audit = get_security_log()
            except Exception:
                self._audit = None
        return self._audit

    def _record(self, event: str, severity: str = "info", **evidence: Any) -> None:
        log = self.audit
        if log is None:
            return
        try:
            log.record("integrity", event, severity=severity, subject="evolution",
                       evidence=evidence, source="evolution")
        except Exception:
            pass

    # -- individual steps -----------------------------------------------------

    def experiment(self, hypothesis: str, harness: str,
                   files: Optional[Dict[str, str]] = None) -> ExperimentResult:
        result = Experiment(hypothesis, harness, files).run()
        self._record("experiment_run", severity="info", experiment_id=result.experiment_id,
                     verdict=result.verdict, hypothesis=hypothesis)
        return result

    def propose(self, title: str, rationale: str, change: Optional[Dict[str, str]] = None,
                evidence: Optional[List[str]] = None) -> EvolutionProposal:
        proposal = self.store.create(title, rationale, change, evidence)
        self._record("proposal_created", proposal_id=proposal.proposal_id,
                     risk=proposal.risk.get("risk_level"), title=title)
        return proposal

    def prove(self, proposal_id: str, cases: List[Dict[str, str]],
              before: Dict[str, str], after: Dict[str, str]) -> RegressionTest:
        test = verify_red_green(f"{proposal_id}-regression", cases, before, after)
        proposal = self.store.get(proposal_id)
        if proposal is not None:
            proposal.regression_tests = {test.name: test.code}
            proposal.evidence = list(proposal.evidence) + [f"regression:{test.outcome}"]
        self._record("regression_verified" if test.outcome == RESULT_RED_GREEN
                     else "regression_rejected",
                     severity="info" if test.outcome == RESULT_RED_GREEN else "medium",
                     proposal_id=proposal_id, outcome=test.outcome)
        return test

    def attack(self, change: Dict[str, str], baseline: Optional[Dict[str, str]] = None,
               probes: Optional[List[Probe]] = None) -> AdversarialReport:
        report = evaluate(change, probes or default_probes(), baseline=baseline)
        self._record("adversarial_clean" if report.ok else "adversarial_regression",
                     severity="info" if report.ok else "high",
                     flags=len(report.static_flags),
                     regressions=sum(1 for r in report.results if r.regression))
        return report

    def prepare_change(self, proposal_id: str, root: Optional[str] = None,
                       owner_approved: bool = False) -> ReversibleChange:
        """Build (and, with approval, apply) a reversible change for a proposal."""
        proposal = self.store.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal '{proposal_id}'")
        base = root or self.repo_root
        before = snapshot(base, sorted(proposal.change))
        change = ReversibleChange(
            change_id=f"chg-{proposal_id}",
            before=before,
            after=dict(proposal.change),
        )
        if owner_approved and proposal.change:
            change.apply(base, owner_approved=True)
        self._record("change_prepared", proposal_id=proposal_id,
                     files=change.files, applied=change.applied)
        return change

    def review(self, proposal_id: str, regression: RegressionTest,
               adversarial: AdversarialReport) -> Dict[str, Any]:
        """Mark a proposal verified/ready iff its evidence actually holds.

        This is the gate: a proposal becomes ``ready`` for owner review only when
        its generated test discriminates (red before, green after) *and* the
        adversarial evaluation is clean. Otherwise it is rejected.
        """
        proposal = self.store.get(proposal_id)
        if proposal is None:
            raise KeyError(f"unknown proposal '{proposal_id}'")
        self.store.update_status(proposal_id, STATUS_EXPERIMENTING)

        verified = regression.outcome == RESULT_RED_GREEN and adversarial.ok
        status = STATUS_VERIFIED if verified else STATUS_REJECTED
        self.store.update_status(proposal_id, status)
        if verified:
            self.store.update_status(proposal_id, STATUS_READY)

        outcome = {
            "proposal_id": proposal_id,
            "status": self.store.get(proposal_id).status,
            "verified": verified,
            "regression_outcome": regression.outcome,
            "adversarial_ok": adversarial.ok,
            "needs_owner_approval": True,
            "owner_review_required": True,
        }
        self._record("proposal_ready" if verified else "proposal_rejected",
                     severity="info" if verified else "medium", **outcome)
        return outcome

    # -- convenience ----------------------------------------------------------

    def run_loop(self, title: str, rationale: str, harness: str,
                 cases: List[Dict[str, str]], change: Dict[str, str],
                 before: Dict[str, str], baseline: Optional[Dict[str, str]] = None,
                 probes: Optional[List[Probe]] = None) -> Dict[str, Any]:
        """Run the whole loop and return the combined evidence.

        The result is *proposed*, not landed: it always carries
        ``needs_owner_approval: True``.
        """
        experiment = self.experiment(rationale, harness, change)
        proposal = self.propose(title, rationale, change,
                                evidence=[f"experiment:{experiment.verdict}"])
        regression = self.prove(proposal.proposal_id, cases, before, change)
        adversarial = self.attack(change, baseline=baseline, probes=probes)
        outcome = self.review(proposal.proposal_id, regression, adversarial)
        outcome["experiment"] = experiment.to_dict()
        outcome["proposal"] = proposal.to_dict()
        outcome["regression"] = regression.to_dict()
        outcome["adversarial"] = adversarial.to_dict()
        return outcome

    def status(self) -> Dict[str, Any]:
        proposals = self.store.list()
        return {
            "proposals": len(proposals),
            "ready_for_review": [p.proposal_id for p in proposals if p.status == STATUS_READY],
            "rejected": [p.proposal_id for p in proposals if p.status == STATUS_REJECTED],
            "store": self.store.path or "(memory)",
            "autonomy": "propose-only (never lands or deploys)",
        }
