"""A first scientific benchmark that can actually be reproduced here.

The directive asks to start with formal proofs and theorem verification. Lean is
the right long-term target, and ``LeanChecker`` is written for it - but Lean is
not installed in this environment, so it reports ``available: False`` and the
benchmark refuses to claim anything from it. Claiming Lean results without Lean
would be exactly the fabrication the constitution forbids.

So the benchmark ships with a checker that *is* real here: exhaustive truth
tables over propositional logic. It has the property that matters - it can say
no. The problem set includes known tautologies *and* negative controls that must
fail; a checker that accepts the controls is reported broken instead of scoring
100%.

Every result records how it was produced:

* ``human``      - the problem statement came from a published list
* ``tool``       - a checker (truth table, Lean) did the verification
* ``autonomous`` - the system generated the candidate and the check

Nothing in this module calls a model. It verifies; it does not generate.
"""
from __future__ import annotations

import itertools
import os
import re
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field

TAUTOLOGY = "tautology"
CONTINGENT = "contingent"
CONTRADICTION = "contradiction"


# --------------------------------------------------------------------------
# Propositional logic: a small parser and an exhaustive evaluator
# --------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"\s*(<->|->|[&|!()]|[a-z][a-z0-9_]*)")


class LogicError(ValueError):
    """The statement is not well formed."""


def _tokenize(text: str) -> list[str]:
    tokens, pos = [], 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise LogicError(f"unexpected character at {pos}: {text[pos]!r}")
        tokens.append(m.group(1))
        pos = m.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.i = 0

    def peek(self) -> str | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def take(self, expected: str | None = None) -> str:
        tok = self.peek()
        if tok is None:
            raise LogicError("unexpected end of statement")
        if expected is not None and tok != expected:
            raise LogicError(f"expected {expected!r}, found {tok!r}")
        self.i += 1
        return tok

    def parse(self):
        node = self.iff()
        if self.peek() is not None:
            raise LogicError(f"trailing tokens from {self.peek()!r}")
        return node

    def iff(self):
        node = self.impl()
        while self.peek() == "<->":
            self.take()
            node = ("iff", node, self.impl())
        return node

    def impl(self):
        node = self.disj()
        if self.peek() == "->":            # right associative
            self.take()
            return ("impl", node, self.impl())
        return node

    def disj(self):
        node = self.conj()
        while self.peek() == "|":
            self.take()
            node = ("or", node, self.conj())
        return node

    def conj(self):
        node = self.unary()
        while self.peek() == "&":
            self.take()
            node = ("and", node, self.unary())
        return node

    def unary(self):
        tok = self.peek()
        if tok == "!":
            self.take()
            return ("not", self.unary())
        if tok == "(":
            self.take()
            node = self.iff()
            self.take(")")
            return node
        if tok and re.fullmatch(r"[a-z][a-z0-9_]*", tok):
            self.take()
            return ("atom", tok)
        raise LogicError(f"unexpected token {tok!r}")


def parse(statement: str):
    """Parse a propositional statement into an AST."""
    if not (statement or "").strip():
        raise LogicError("empty statement")
    return _Parser(_tokenize(statement)).parse()


def atoms(node) -> set:
    kind = node[0]
    if kind == "atom":
        return {node[1]}
    if kind == "not":
        return atoms(node[1])
    return atoms(node[1]) | atoms(node[2])


def evaluate(node, env: dict[str, bool]) -> bool:
    kind = node[0]
    if kind == "atom":
        return bool(env[node[1]])
    if kind == "not":
        return not evaluate(node[1], env)
    if kind == "and":
        return evaluate(node[1], env) and evaluate(node[2], env)
    if kind == "or":
        return evaluate(node[1], env) or evaluate(node[2], env)
    if kind == "impl":
        return (not evaluate(node[1], env)) or evaluate(node[2], env)
    if kind == "iff":
        return evaluate(node[1], env) == evaluate(node[2], env)
    raise LogicError(f"unknown node {kind!r}")


def classify(statement: str) -> tuple[str, dict[str, bool] | None]:
    """Exhaustively classify a statement, returning a counterexample if any."""
    node = parse(statement)
    names = sorted(atoms(node))
    seen_true = seen_false = False
    witness: dict[str, bool] | None = None
    for values in itertools.product([False, True], repeat=len(names)):
        env = dict(zip(names, values, strict=True))
        if evaluate(node, env):
            seen_true = True
        else:
            seen_false = True
            if witness is None:
                witness = env
    if seen_true and not seen_false:
        return TAUTOLOGY, None
    if seen_false and not seen_true:
        return CONTRADICTION, witness
    return CONTINGENT, witness


# --------------------------------------------------------------------------
# Checkers
# --------------------------------------------------------------------------
@dataclass
class CheckResult:
    passed: bool
    detail: str = ""
    available: bool = True

    def to_dict(self) -> dict:
        return {"passed": self.passed, "detail": self.detail, "available": self.available}


class TruthTableChecker:
    """Real, exhaustive, and able to say no."""

    name = "truth_table"

    def check(self, statement: str, expected: str = TAUTOLOGY) -> CheckResult:
        try:
            actual, witness = classify(statement)
        except LogicError as exc:
            return CheckResult(False, f"not well formed: {exc}")
        ok = actual == expected
        detail = f"classified {actual}"
        if not ok and witness:
            detail += f"; counterexample {witness}"
        return CheckResult(ok, detail)


class LeanChecker:
    """Lean 4 adapter. Reports unavailable rather than pretending.

    Lean is a state-changing CLI, so it runs only through the single CLI gate
    (``tools/cli_guard``), which requires the owner's identity and a scoped
    approval. Without them the check is refused, not silently skipped - and with
    no Lean binary installed nothing is run at all.
    """

    name = "lean"

    def __init__(self, binary: str | None = None):
        self.binary = binary or shutil.which("lean")

    @property
    def available(self) -> bool:
        return bool(self.binary and os.path.exists(self.binary))

    def check(self, statement: str, expected: str = "theorem",
              *, user_id: int | None = None,
              approval_id: str | None = None) -> CheckResult:
        if not self.available:
            return CheckResult(False, "lean is not installed; no Lean claim is made",
                               available=False)
        source = statement if statement.strip().startswith("example") else \
            f"example : {statement} := by decide\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Claim.lean")
            with open(path, "w") as f:
                f.write(source + "\n")
            from genesis_protocol.tools.cli_guard import run_guarded_command
            outcome = run_guarded_command(self.binary, [path], user_id=user_id,
                                          approval_id=approval_id, timeout=120)
        if outcome.get("denied"):
            return CheckResult(False, f"refused by the CLI gate: {outcome.get('error')}")
        if not outcome.get("success"):
            detail = (outcome.get("stdout") or outcome.get("stderr")
                      or outcome.get("error") or "").strip()
            return CheckResult(False, detail[:500])
        return CheckResult(True, (outcome.get("stdout") or "").strip()[:500])


# --------------------------------------------------------------------------
# Problems
# --------------------------------------------------------------------------
@dataclass
class Problem:
    id: str
    statement: str
    expected: str
    note: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "statement": self.statement,
                "expected": self.expected, "note": self.note}


#: Published propositional identities (tautologies) plus negative controls. The
#: controls are the point: a checker that cannot reject them is worthless.
PROBLEMS: list[Problem] = [
    Problem("de_morgan_1", "!(a & b) <-> (!a | !b)", TAUTOLOGY, "De Morgan"),
    Problem("de_morgan_2", "!(a | b) <-> (!a & !b)", TAUTOLOGY, "De Morgan"),
    Problem("double_negation", "!!a <-> a", TAUTOLOGY, "involution"),
    Problem("excluded_middle", "a | !a", TAUTOLOGY, "classical"),
    Problem("non_contradiction", "!(a & !a)", TAUTOLOGY, "classical"),
    Problem("contraposition", "(a -> b) <-> (!b -> !a)", TAUTOLOGY, "contrapositive"),
    Problem("exportation", "((a & b) -> c) <-> (a -> (b -> c))", TAUTOLOGY, "exportation"),
    Problem("distribution", "(a & (b | c)) <-> ((a & b) | (a & c))", TAUTOLOGY, "distributivity"),
    Problem("absorption", "(a & (a | b)) <-> a", TAUTOLOGY, "absorption"),
    Problem("peirce", "((a -> b) -> a) -> a", TAUTOLOGY, "Peirce's law"),
    # negative controls - must NOT be classified as tautologies
    Problem("control_contingent", "a -> b", CONTINGENT, "negative control"),
    Problem("control_conjunction", "a & b", CONTINGENT, "negative control"),
    Problem("control_contradiction", "a & !a", CONTRADICTION, "negative control"),
]


@dataclass
class BenchmarkReport:
    checker: str
    results: list[dict] = field(default_factory=list)
    checker_discriminating: bool = False
    available: bool = True
    assisted_by: str = "tool"
    probes: dict = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return len([r for r in self.results if r["passed"]])

    @property
    def total(self) -> int:
        return len(self.results)

    def to_dict(self) -> dict:
        return {
            "checker": self.checker,
            "passed": self.passed,
            "total": self.total,
            "checker_discriminating": self.checker_discriminating,
            "available": self.available,
            "assisted_by": self.assisted_by,
            "probes": dict(self.probes),
            "results": list(self.results),
            # a benchmark score is not a discovery, and never becomes one
            "is_discovery": False,
        }


def run_benchmark(checker=None, problems: Sequence[Problem] | None = None) -> BenchmarkReport:
    """Run the problem set against ``checker`` (truth table by default).

    Before scoring, the checker is put through two probes: it must accept a
    tautology and *reject* a contradiction presented as a tautology. A checker
    that says yes to both is a yes-man - it would score 100% on any problem set
    and prove nothing - so it is reported as non-discriminating instead.
    """
    checker = checker or TruthTableChecker()
    items = list(problems or PROBLEMS)
    report = BenchmarkReport(checker=getattr(checker, "name", "unknown"))

    probe_pass = checker.check("a | !a", TAUTOLOGY)
    probe_fail = checker.check("a & !a", TAUTOLOGY)
    report.available = bool(probe_pass.available and probe_fail.available)
    report.probes = {
        "accepts_tautology": probe_pass.passed,
        "rejects_false_tautology": not probe_fail.passed,
    }
    report.checker_discriminating = bool(
        report.available and probe_pass.passed and not probe_fail.passed
    )

    for problem in items:
        result = checker.check(problem.statement, problem.expected)
        report.results.append({
            **problem.to_dict(),
            "passed": result.passed,
            "detail": result.detail,
            "available": result.available,
        })
        if not result.available:
            report.available = False
    return report
