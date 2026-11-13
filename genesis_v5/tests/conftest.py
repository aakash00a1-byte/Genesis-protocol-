"""Make the genesis_v5 package importable when its suite runs.

These tests import the top-level ``genesis`` package (``from genesis.core
import ...``), which lives under ``genesis_v5/``. Without this, collection dies
with ``ModuleNotFoundError: No module named 'genesis'`` — which is why the suite
was invisible for so long: it never ran, so nothing it guards was actually
covered, and the evolution loop could report real, tested code as "untested".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
