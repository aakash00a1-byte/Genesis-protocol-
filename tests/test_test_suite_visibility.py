"""Guard the two test suites stay runnable together.

For a long time CI (and the self-improve verification gate) ran only
``pytest tests/``. The V6 kernel suite in ``genesis_v5/tests/`` was never
executed, so code that was in fact tested could be reported — and believed —
as "untested". These assertions fail loudly if the configuration that makes
both suites run is ever undone.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _pytest_config() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["tool"]["pytest"]["ini_options"]


def test_testpaths_cover_both_suites() -> None:
    testpaths = _pytest_config().get("testpaths", [])
    assert "tests" in testpaths
    assert "genesis_v5/tests" in testpaths


def test_import_mode_is_importlib() -> None:
    # tests/ and genesis_v5/tests/ share basenames; default prepend mode would
    # shadow one with the other.
    assert "--import-mode=importlib" in _pytest_config().get("addopts", "")


def test_v6_conftest_puts_genesis_on_path() -> None:
    conftest = ROOT / "genesis_v5" / "tests" / "conftest.py"
    assert conftest.exists()
    assert "sys.path.insert" in conftest.read_text(encoding="utf-8")


def test_workflows_do_not_pin_a_single_test_path() -> None:
    """A pinned ``pytest tests/`` is exactly the bug; forbid it in CI + gate."""
    for name in ("ci.yml", "self-improve.yml"):
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "pytest tests/ -q" not in text, (
            f"{name} pins only tests/; the V6 suite would stop running"
        )
