"""Make the top-level ``genesis`` package importable when the suite runs.

These tests do ``from genesis.core import ...``. That package lives under
``genesis_v5/``; neither the repo root nor the installed environment exposes it,
so collection would die with ``ModuleNotFoundError: No module named 'genesis'``.
That is one of the reasons the suite never ran.

The other requirement — the sandbox root ``/workspace`` with the checkout at
``/workspace/project`` — is provided by the runner (CI bind-mounts the checkout
there). It cannot be faked with a symlink: the sandbox resolves symlinks with
``realpath`` on purpose, so a linked ``/workspace/project`` is correctly judged
"outside the sandbox".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "genesis_v5"))

