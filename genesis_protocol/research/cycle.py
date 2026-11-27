"""The research cycle, as an ordered gate rather than a checklist.

    question -> literature -> hypothesis -> model -> experiment
             -> measurement -> verification -> report

Each stage must be completed in order, with evidence, and the cycle refuses to
move on without it. The two gates that matter most:

* **verification** needs a checker result that passed *and* is independent of
  whatever produced the result. A result checking itself is not verification.
* **report** needs a verified result. There is no path to a report that skips
  verification, so there is no path to a claim that skips it either.

Every transition is appended to the ledger, so the history of a cycle is
reconstructible. Nothing here executes code or calls a model: it decides whether
the evidence on hand is enough to advance, and says no when it is not.
"""
from __future__ import annotations

from collections.abc import Sequence

from .ledger import ResearchLedger

STAGES: Sequence[str] = (
    "question",
    "literature",
    "hypothesis",
    "model",
    "experiment",
    "measurement",
    "verification",
    "report",
)

#: What each stage must supply. Empty tuple means "any non-empty evidence".
REQUIRED: dict[str, Sequence[str]] = {
    "question": ("question", "why_it_matters"),
    "literature": ("sources", "summary"),
    "hypothesis": ("statement", "falsifiable_test"),
    "model": ("formalism", "prediction"),
    "experiment": ("design", "procedure"),
    "measurement": ("observations", "units"),
    "verification": ("checker", "passed", "independent"),
    "report": ("path", "summary"),
}


class ResearchError(ValueError):
    """Base class for a refused research transition."""


class StageOrderError(ResearchError):
    """A stage was attempted out of order."""


class MissingEvidenceError(ResearchError):
    """A stage was attempted without its required evidence."""


class VerificationRequiredError(ResearchError):
    """A claim was attempted without an independent, passing check."""


def _missing(stage: str, evidence: dict) -> list[str]:
    gaps = []
    for key in REQUIRED.get(stage, ()):
        value = evidence.get(key)
        if value is None:
            gaps.append(key)
        elif isinstance(value, (str, list, tuple, dict)) and len(value) == 0:
            gaps.append(key)
    return gaps


class ResearchCycle:
    """One research question, advanced stage by stage."""

    def __init__(self, cycle_id: str, ledger: ResearchLedger | None = None):
        self.id = cycle_id
        self.ledger = ledger or ResearchLedger()
        self.completed: list[str] = []
        self.records: dict[str, dict] = {}
        self.ledger.append(self.id, "cycle_opened", {"stages": list(STAGES)})

    # -- state --------------------------------------------------------------
    @property
    def stage(self) -> str:
        return STAGES[len(self.completed)] if len(self.completed) < len(STAGES) else "done"

    def status(self) -> dict:
        blockers: list[str] = []
        if self.stage != "done":
            blockers = list(REQUIRED.get(self.stage, ()))
        return {
            "cycle": self.id,
            "stage": self.stage,
            "completed": list(self.completed),
            "next_requires": blockers,
            "verified": self._has_verified_result(),
            "ledger": self.ledger.verify(),
        }

    # -- transitions --------------------------------------------------------
    def advance(self, stage: str, **evidence) -> dict:
        """Complete ``stage`` with ``evidence``, or refuse and say why."""
        if stage not in STAGES:
            raise StageOrderError(f"unknown stage '{stage}'")
        expected = self.stage
        if expected == "done":
            raise StageOrderError("the cycle is complete; start a new one")
        if stage != expected:
            raise StageOrderError(
                f"stage '{stage}' attempted out of order; expected '{expected}'"
            )
        gaps = _missing(stage, evidence)
        if gaps:
            raise MissingEvidenceError(
                f"stage '{stage}' needs {', '.join(gaps)}"
            )
        if stage == "verification":
            self._require_independent_check(evidence)
        if stage == "report" and not self._has_verified_result():
            raise VerificationRequiredError(
                "a report requires a verified result; run the verification stage first"
            )

        record = {"stage": stage, "evidence": dict(evidence)}
        self.records[stage] = record
        self.completed.append(stage)
        self.ledger.append(self.id, f"stage:{stage}", record)
        return record

    # -- helpers ------------------------------------------------------------
    def _require_independent_check(self, evidence: dict) -> None:
        if evidence.get("passed") is not True:
            raise VerificationRequiredError("verification did not pass")
        if evidence.get("independent") is not True:
            raise VerificationRequiredError(
                "verification must be independent of whatever produced the result"
            )
        checker = str(evidence.get("checker", "")).strip()
        producer = str(evidence.get("produced_by", "")).strip()
        if checker and producer and checker.lower() == producer.lower():
            raise VerificationRequiredError(
                f"'{checker}' cannot verify its own output"
            )

    def _has_verified_result(self) -> bool:
        record = self.records.get("verification")
        return bool(record and record["evidence"].get("passed") is True
                    and record["evidence"].get("independent") is True)

    # -- claims -------------------------------------------------------------
    def can_claim_discovery(self) -> dict:
        """A discovery claim needs a written report *and* a verified result."""
        has_report = "report" in self.records
        verified = self._has_verified_result()
        return {
            "claim_allowed": bool(has_report and verified),
            "report_written": has_report,
            "verified": verified,
            "reason": ("report written and result independently verified"
                       if has_report and verified else
                       "no claim: " + ("report missing" if not has_report else "result not verified")),
        }
