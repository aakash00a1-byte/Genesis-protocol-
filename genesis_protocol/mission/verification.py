"""Result verification (V7 P10).

A task is not done because it said so. This module checks a task's result
against its acceptance criteria with deterministic, declarative checks, and
fails closed: an unknown check, a missing field, or an unverifiable claim is a
failure, never a pass.

Supported checks (a list of ``{op: [args]}``):

* ``equals``      - ``result.<path>`` equals a value;
* ``contains``    - ``result.<path>`` contains a substring / element;
* ``truthy``      - ``result.<path>`` is truthy;
* ``nonempty``    - ``result.<path>`` is a non-empty collection or string;
* ``min``/``max`` - ``result.<path>`` is a number within a bound.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

KNOWN_OPS = {"equals", "contains", "truthy", "nonempty", "min", "max"}


@dataclass
class VerificationOutcome:
    ok: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ResultVerifier:
    """Verifies a task result against declarative checks."""

    def verify(self, result: Any, checks: Optional[List[Dict[str, Any]]] = None,
               require_success: bool = True) -> VerificationOutcome:
        reasons: List[str] = []

        if result is None:
            return VerificationOutcome(False, ["no result was produced"])

        if not isinstance(result, dict):
            return VerificationOutcome(False, ["result is not a mapping"])

        if require_success and not (result.get("success") or result.get("ok")):
            reasons.append("result did not report success")

        for index, check in enumerate(checks or []):
            if not isinstance(check, dict) or len(check) != 1:
                reasons.append(f"check {index} is malformed")
                continue
            op, args = next(iter(check.items()))
            if op not in KNOWN_OPS:
                reasons.append(f"check {index}: unknown operation '{op}'")
                continue
            reason = self._apply(op, args, result)
            if reason:
                reasons.append(f"check {index} ({op}): {reason}")

        return VerificationOutcome(not reasons, reasons)

    def _apply(self, op: str, args: Any, result: Dict[str, Any]) -> Optional[str]:
        if not isinstance(args, list) or not args:
            return "no arguments"
        path = str(args[0])
        value = _lookup(result, path)
        if value is _MISSING:
            return f"missing field '{path}'"

        if op == "truthy":
            return None if value else f"'{path}' is falsy"
        if op == "nonempty":
            return None if value else f"'{path}' is empty"
        if op == "equals":
            if len(args) < 2:
                return "equals needs a value"
            return None if value == args[1] else f"'{path}' != {args[1]!r}"
        if op == "contains":
            if len(args) < 2:
                return "contains needs a value"
            try:
                return None if args[1] in value else f"'{path}' does not contain {args[1]!r}"
            except TypeError:
                return f"'{path}' is not containable"
        if op in ("min", "max"):
            if len(args) < 2 or not isinstance(args[1], (int, float)):
                return f"{op} needs a numeric bound"
            try:
                number = float(value)
            except (TypeError, ValueError):
                return f"'{path}' is not numeric"
            if op == "min" and number < args[1]:
                return f"'{path}' {number} < {args[1]}"
            if op == "max" and number > args[1]:
                return f"'{path}' {number} > {args[1]}"
            return None
        return f"unhandled operation '{op}'"


class _Missing:
    pass


_MISSING = _Missing()


def _lookup(obj: Any, path: str) -> Any:
    """Resolve a dotted path (``a.b.0.c``) within nested mappings/sequences."""
    current = obj
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if not part.isdigit() or int(part) >= len(current):
                return _MISSING
            current = current[int(part)]
        else:
            return _MISSING
    return current
