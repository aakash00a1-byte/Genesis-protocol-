"""Generated regression tests (V7 P9).

An improvement is only trustworthy if a test proves it. P9 *generates* that
test and then checks it is meaningful with a red/green run:

* **red**  - the test must FAIL against the current (pre-change) code, otherwise
  it does not actually exercise the defect;
* **green** - the test must PASS against the proposed (post-change) code.

Both runs happen in the canonical sandbox against scratch trees, so nothing in
the repository is modified. A test that is green in both runs is reported as
``not_discriminating`` rather than silently accepted.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from genesis_protocol.agentic.sandbox import run_python
from genesis_protocol.evolution.experiment import utcnow

RESULT_RED_GREEN = "red_green"
RESULT_NOT_DISCRIMINATING = "not_discriminating"
RESULT_BROKEN = "broken"

_HEADER = '''"""Generated regression test (V7 P9). Do not edit by hand."""
import json
import os
import sys

# The sandbox runs an isolated interpreter whose script lives elsewhere, so the
# scratch tree (cwd) is not importable by default. Add it explicitly.
sys.path.insert(0, os.getcwd())

_RESULTS = []


def check(name, fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        _RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))
    else:
        _RESULTS.append((name, True, ""))


def main():
    for name, fn in TESTS:
        check(name, fn)
    failed = [r for r in _RESULTS if not r[1]]
    for name, ok, err in _RESULTS:
        print("OBS: %s %s%s" % (name, "PASS" if ok else "FAIL", (" - " + err) if err else ""))
    print(json.dumps({"passed": len(_RESULTS) - len(failed), "failed": len(failed)}))
    sys.exit(1 if failed else 0)


TESTS = []


'''

_FOOTER = '''

if __name__ == "__main__":
    main()
'''


@dataclass
class RegressionTest:
    """A generated regression test with its red/green evidence."""

    name: str
    code: str
    created_at: str = field(default_factory=utcnow)
    outcome: str = ""
    red: Optional[bool] = None
    green: Optional[bool] = None
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_test_module(name: str, cases: List[Dict[str, str]]) -> str:
    """Build a self-contained test module from ``{name, code}`` cases.

    Each case body is an assertion block; a raised exception is a failure. The
    module prints ``OBS:`` lines and a JSON summary and exits non-zero on any
    failure, so it runs under the isolated sandbox without pytest.
    """
    if not cases:
        raise ValueError("a regression test needs at least one case")
    lines = [_HEADER]
    registrations = []
    for index, case in enumerate(cases):
        case_name = (case.get("name") or f"case_{index}").strip()
        body = (case.get("code") or "").strip("\n")
        if not body.strip():
            raise ValueError(f"case '{case_name}' has no code")
        fn = f"case_{index}"
        lines.append(f"def {fn}():\n")
        for body_line in body.splitlines():
            lines.append(f"    {body_line}\n")
        lines.append("\n\n")
        registrations.append(f'TESTS.append(("{case_name}", {fn}))')
    lines.append("\n".join(registrations) + "\n")
    lines.append(_FOOTER)
    return "".join(lines)


def _run(module: str, files: Dict[str, str], timeout: float) -> Any:
    import tempfile
    from pathlib import Path

    scratch = tempfile.mkdtemp(prefix="genesis_regression_")
    for rel, content in files.items():
        target = Path(scratch) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (Path(scratch) / "test_generated.py").write_text(module, encoding="utf-8")
    return run_python(module, timeout=timeout, workdir=scratch)


def verify_red_green(
    name: str,
    cases: List[Dict[str, str]],
    before: Dict[str, str],
    after: Dict[str, str],
    timeout: float = 20.0,
) -> RegressionTest:
    """Prove a generated test fails on ``before`` and passes on ``after``."""
    module = generate_test_module(name, cases)
    test = RegressionTest(name=name, code=module)

    red_run = _run(module, before, timeout)
    green_run = _run(module, after, timeout)

    test.red = not red_run.success
    test.green = bool(green_run.success)
    test.detail = _summarise(red_run, green_run)

    if test.green and test.red:
        test.outcome = RESULT_RED_GREEN
    elif test.green and not test.red:
        # Passes even without the change: it does not exercise the defect.
        test.outcome = RESULT_NOT_DISCRIMINATING
    else:
        test.outcome = RESULT_BROKEN
    return test


def _summarise(red_run: Any, green_run: Any) -> str:
    return json.dumps({
        "before_exit": red_run.exit_code,
        "after_exit": green_run.exit_code,
        "before_stdout": (red_run.stdout or "").strip()[-500:],
        "after_stdout": (green_run.stdout or "").strip()[-500:],
        "before_error": red_run.error,
        "after_error": green_run.error,
    }, default=str)
