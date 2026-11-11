"""AST-validated evaluation of math expressions.

``eval`` is unsafe for math expressions even with ``__builtins__`` removed and
only ``math`` in scope: attribute and subclass traversal still reaches arbitrary
callables, e.g. ``().__class__.__mro__[1].__subclasses__()``, which yields
``os`` and therefore command execution. Substring filters on the expression
(such as rewriting ``e`` to Euler's number) are bypassed with ``'%c' % 101``.

This module instead parses the expression and walks a whitelist of AST nodes,
so only numeric literals, arithmetic, unary +/-, the constants below and
``math`` functions can appear.
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable, Dict

MAX_EXPRESSION_LENGTH = 1000
MAX_POWER_EXPONENT = 1000

_BINARY_OPS: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    # The calculator has always accepted '^' as exponentiation.
    ast.BitXor: operator.pow,
}
_UNARY_OPS: Dict[type, Callable[[Any], Any]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_CONSTANTS: Dict[str, float] = {"pi": math.pi, "e": math.e, "tau": math.tau}
_FUNCTIONS: Dict[str, Callable[..., Any]] = {
    name: getattr(math, name) for name in dir(math) if not name.startswith("_")
}


class MathExpressionError(ValueError):
    """Raised when an expression is empty, malformed or not whitelisted."""


def safe_math_eval(expression: str) -> Any:
    """Evaluate a math expression, rejecting anything outside the whitelist."""
    if not isinstance(expression, str) or not expression.strip():
        raise MathExpressionError("empty expression")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise MathExpressionError("expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise MathExpressionError(f"invalid expression: {exc.msg}") from exc
    return _evaluate(tree.body)


def _evaluate(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, complex)):
            raise MathExpressionError("only numeric literals are allowed")
        return node.value

    if isinstance(node, ast.BinOp):
        op = _BINARY_OPS.get(type(node.op))
        if op is None:
            raise MathExpressionError(f"operator '{type(node.op).__name__}' is not allowed")
        left, right = _evaluate(node.left), _evaluate(node.right)
        if isinstance(node.op, (ast.Pow, ast.BitXor)) and isinstance(right, (int, float)) and abs(right) > MAX_POWER_EXPONENT:
            raise MathExpressionError("exponent too large")
        return op(left, right)

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise MathExpressionError(f"operator '{type(node.op).__name__}' is not allowed")
        return op(_evaluate(node.operand))

    if isinstance(node, ast.Name):
        if node.id not in _CONSTANTS:
            raise MathExpressionError(f"name '{node.id}' is not allowed")
        return _CONSTANTS[node.id]

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise MathExpressionError("only math functions may be called")
        if node.keywords:
            raise MathExpressionError("keyword arguments are not allowed")
        return _FUNCTIONS[node.func.id](*[_evaluate(arg) for arg in node.args])

    raise MathExpressionError(f"unsupported expression: {type(node).__name__}")
