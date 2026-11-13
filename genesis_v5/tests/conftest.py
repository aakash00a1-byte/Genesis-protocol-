"""Make the genesis_v5 suite runnable wherever it is checked out.

Two things the suite needs that no runner provides by default:

1. the top-level ``genesis`` package (``from genesis.core import ...``), which
   lives under ``genesis_v5/`` — without it, collection dies with
   ``ModuleNotFoundError: No module named 'genesis'``;
2. the production sandbox layout: the tools are allowed under ``/workspace``
   and several tests read ``/workspace/project/...``. The container supplies
   this, CI and the self-improve verification gate do not.

Missing either made the suite uncollectable or red, which is why it was never
run — and why genuinely-tested code could be reported as "untested". Point
``/workspace/project`` at this checkout's root so the tests always exercise the
code under test (the worktree in the gate, not some stale copy).
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]  # <repo or worktree>/genesis_v5/..
sys.path.insert(0, str(_ROOT / "genesis_v5"))

_SANDBOX = Path("/workspace")


def _ensure_sandbox_layout() -> None:
    """Best-effort: expose this checkout as ``/workspace/project``.

    ``/workspace`` itself is created by the runner (it needs root); if it is
    absent we cannot help, and the tests that need it fail loudly rather than
    being silently skipped.
    """
    if not _SANDBOX.is_dir():
        return
    link = _SANDBOX / "project"
    if link.is_symlink() and Path(link).resolve() == _ROOT:
        return
    if link.exists() and not link.is_symlink():
        return
    try:
        if link.is_symlink():
            link.unlink()
        link.symlink_to(_ROOT)
    except OSError:
        pass


_ensure_sandbox_layout()

