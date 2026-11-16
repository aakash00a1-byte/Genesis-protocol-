"""Isolated experiments (V7 P9).

An experiment is a candidate change that is evaluated *without touching the
repository*. It runs in the canonical sandbox (``agentic.sandbox.run_python``:
isolated interpreter, bounded time/memory/CPU/output) against a scratch copy of
the files it declares, so a bad change cannot damage the tree it came from.

The module records a full :class:`ExperimentResult` - the change, the observed
outcome, the resource cost and a verdict - which the rest of P9 treats as
evidence. Nothing here writes to the working tree, applies a patch, or grants
authority.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.sandbox import run_python

VERDICT_PASSED = "passed"
VERDICT_FAILED = "failed"
VERDICT_ERROR = "error"
VERDICT_SKIPPED = "skipped"

DEFAULT_TIMEOUT = 20.0
DEFAULT_MEMORY_MB = 256
DEFAULT_CPU_SECONDS = 20
MAX_FILES = 64
MAX_FILE_BYTES = 256 * 1024


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ExperimentResult:
    """Evidence from one isolated experiment."""

    experiment_id: str
    hypothesis: str
    verdict: str
    started_at: str
    finished_at: str
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    timed_out: bool = False
    files_touched: List[str] = field(default_factory=list)
    limits: Dict[str, Any] = field(default_factory=dict)
    observations: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == VERDICT_PASSED

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["ok"] = self.ok
        return data


class Experiment:
    """One isolated, reproducible trial of a candidate change.

    ``files`` maps a repo-relative path to its *proposed* content. The experiment
    materialises those files (and only those) into a scratch directory, plus a
    harness script, and runs the harness in the sandbox. The repository is never
    written.
    """

    def __init__(
        self,
        hypothesis: str,
        harness: str,
        files: Optional[Dict[str, str]] = None,
        experiment_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        memory_mb: int = DEFAULT_MEMORY_MB,
        cpu_seconds: int = DEFAULT_CPU_SECONDS,
    ):
        if not (hypothesis or "").strip():
            raise ValueError("an experiment requires a hypothesis")
        if not (harness or "").strip():
            raise ValueError("an experiment requires a harness to run")
        self.hypothesis = hypothesis.strip()
        self.harness = harness
        self.files = _validate_files(files or {})
        self.experiment_id = experiment_id or f"exp-{utcnow().replace(':', '').replace('-', '')}"
        self.timeout = timeout
        self.memory_mb = memory_mb
        self.cpu_seconds = cpu_seconds

    def run(self, workdir: Optional[str] = None) -> ExperimentResult:
        """Execute the harness in an isolated scratch tree and capture evidence."""
        started = utcnow()
        scratch = workdir or tempfile.mkdtemp(prefix="genesis_experiment_")
        created = Path(scratch)
        for rel, content in self.files.items():
            target = created / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        result = run_python(
            self.harness,
            timeout=self.timeout,
            memory_mb=self.memory_mb,
            cpu_seconds=self.cpu_seconds,
            workdir=str(created),
        )

        if result.timed_out:
            verdict = VERDICT_ERROR
        elif result.success:
            verdict = VERDICT_PASSED
        elif result.error:
            verdict = VERDICT_ERROR
        else:
            verdict = VERDICT_FAILED

        return ExperimentResult(
            experiment_id=self.experiment_id,
            hypothesis=self.hypothesis,
            verdict=verdict,
            started_at=started,
            finished_at=utcnow(),
            duration_ms=result.duration_ms,
            stdout=result.stdout,
            stderr=result.stderr,
            error=result.error,
            timed_out=result.timed_out,
            files_touched=sorted(self.files),
            limits={
                "timeout_s": self.timeout,
                "memory_mb": self.memory_mb,
                "cpu_seconds": self.cpu_seconds,
            },
            observations=_observations(result.stdout),
        )


def _validate_files(files: Dict[str, str]) -> Dict[str, str]:
    if len(files) > MAX_FILES:
        raise ValueError(f"too many files ({len(files)} > {MAX_FILES})")
    clean: Dict[str, str] = {}
    for rel, content in files.items():
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"file path escapes the experiment root: {rel}")
        blob = content if isinstance(content, str) else str(content)
        if len(blob.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError(f"file too large for an experiment: {rel}")
        clean[rel] = blob
    return clean


def _observations(stdout: str) -> List[str]:
    """Pull explicit ``OBS:`` lines out of the harness output as observations."""
    out: List[str] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("OBS:"):
            out.append(line[4:].strip())
    return out


def make_result(payload: Dict[str, Any]) -> ExperimentResult:
    """Rebuild an :class:`ExperimentResult` from stored JSON."""
    known = {f for f in ExperimentResult.__dataclass_fields__}
    return ExperimentResult(**{k: v for k, v in payload.items() if k in known})


def dumps(result: ExperimentResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True, default=str)


def env_without_secrets() -> Dict[str, str]:
    """A reminder of the contract: experiments never receive secrets.

    The sandbox already scrubs the environment; this helper exists so callers
    can assert the invariant explicitly in tests.
    """
    return {k: v for k, v in os.environ.items() if not any(
        token in k.upper() for token in ("TOKEN", "KEY", "SECRET", "PASSWORD")
    )}
