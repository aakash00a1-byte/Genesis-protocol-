"""Regression tests for the calculator tools.

These lock in the fix for a critical sandbox escape: the previous
implementation built an expression string and passed it to ``eval`` with only
``math`` in scope. Attribute/subclass traversal still reached ``os``
(``().__class__.__mro__[1].__subclasses__()``), and the ``e`` -> Euler's-number
rewrite was bypassable with ``'%c' % 101``. A non-owner could therefore run
arbitrary commands through ``/api/agent/run``.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis_protocol.tools.safe_math import MathExpressionError, safe_math_eval


def _e_free_escape_payload(marker: str) -> str:
    """Rebuild the exploit that defeated the old substring filter."""
    E = "('%c'%101)"
    OBJ = "().__class__.__mro__[1]"
    TYP = "().__class__.__class__"
    idx = [c.__name__ for c in object.__subclasses__()].index("BuiltinImporter")
    cls = f"{TYP}.__dict__['__subclass'+{E}+'s__']({OBJ})[{idx}]"
    return (
        f"{cls}.__dict__['load_modul'+{E}].__func__({cls},'os')"
        f".__dict__['syst'+{E}+'m']('touch {marker}')"
    )


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2+2", 4),
        ("2**10", 1024),
        ("sqrt(16)", 4.0),
        ("sin(pi/2)", 1.0),
        ("-3", -3),
        ("7 % 3", 1),
        ("10 / 4", 2.5),
    ],
)
def test_valid_expressions_still_evaluate(expression, expected):
    assert safe_math_eval(expression) == pytest.approx(expected)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').getcwd()",
        "().__class__.__bases__[0].__subclasses__()",
        "open('/etc/passwd').read()",
        "().__class__.__mro__[1]",
        "lambda: 1",
        "[x for x in (1,)]",
        "globals()",
        "f'{1}'",
        "1 if 1 else 2",
        "x",
    ],
)
def test_dangerous_expressions_are_rejected(expression):
    with pytest.raises(MathExpressionError):
        safe_math_eval(expression)


def test_e_free_sandbox_escape_is_rejected(tmp_path):
    """The exact bypass that defeated the old filter must not execute."""
    marker = tmp_path / "pwned"
    with pytest.raises(MathExpressionError):
        safe_math_eval(_e_free_escape_payload(str(marker)))
    assert not marker.exists()


def test_calculator_tool_rejects_escape_payload(tmp_path):
    from genesis_protocol.tools.tool_registry import get_tool_registry

    marker = tmp_path / "pwned_tool"
    tool = get_tool_registry().get_tool("calculator")
    result = tool.execute(_e_free_escape_payload(str(marker)))
    assert result["success"] is False
    assert not marker.exists()


def test_non_owner_cannot_execute_through_agent_loop(tmp_path):
    """End-to-end: a non-owner tool step must not reach the shell."""
    os.environ.setdefault("GLUTEN_OWNER_IDS", "1")
    os.environ.setdefault("SECRET_KEY", "test")
    from genesis_protocol.agentic.agent_loop import AgentLoop

    marker = tmp_path / "pwned_loop"
    result = AgentLoop().run(
        user_id=999,
        goal="math",
        steps=[
            {
                "type": "tool",
                "tool": "calculator",
                "params": {"expression": _e_free_escape_payload(str(marker))},
            }
        ],
    )
    step = result["steps"][0]
    assert step.get("success") is False
    assert not marker.exists()
