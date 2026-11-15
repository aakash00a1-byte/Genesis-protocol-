"""The quarantined legacy modules stay out of the production package.

V7 P1 moved five dangerous, unused packages out of ``genesis_protocol/`` into
``quarantine/genesis_protocol/``. These tests hold the isolation contract so a
future change cannot quietly re-expose them:

* the old import paths fail (no compatibility shim);
* no production entry point pulls a quarantined module into ``sys.modules``;
* package discovery (what ``scripts/health_check.py`` walks) does not list them;
* the production runtime, Telegram/web surfaces and the fail-closed tool policy
  are unchanged by the move.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
QUARANTINE_ROOT = ROOT / "quarantine" / "genesis_protocol"
PACKAGE_ROOT = ROOT / "genesis_protocol"

QUARANTINED = ("agent", "autonomy", "deploy", "self_sustaining", "financial")

# The production entry points the application actually loads.
PRODUCTION_ENTRYPOINTS = (
    "web.app",
    "genesis_protocol.updates",
    "genesis_protocol.integrations.telegram_commands",
    "genesis_protocol.ai.tool_system",
    "genesis_protocol.agentic.identity",
)


def _in_subprocess(code: str) -> subprocess.CompletedProcess:
    """Run ``code`` in a fresh interpreter rooted at the repo (clean sys.modules)."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env.pop("SECRET_KEY", None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


class TestQuarantineLocation:
    """The files exist in quarantine and nowhere inside the package."""

    @pytest.mark.parametrize("name", QUARANTINED)
    def test_moved_files_live_under_quarantine(self, name):
        src = QUARANTINE_ROOT / name
        assert src.is_dir(), f"quarantine/{name} missing"
        assert any(src.rglob("*.py")), f"quarantine/{name} has no modules"

    @pytest.mark.parametrize("name", QUARANTINED)
    def test_removed_from_production_package(self, name):
        assert not (PACKAGE_ROOT / name).exists(), (
            f"genesis_protocol/{name} still exists; it must live only in quarantine/"
        )

    def test_no_import_shim_in_package(self):
        """No module inside the package imports a quarantined path."""
        import ast

        def references_quarantined(module: str) -> str | None:
            for name in QUARANTINED:
                target = f"genesis_protocol.{name}"
                # Segment-aware: "genesis_protocol.agent" must not match
                # "genesis_protocol.agentic".
                if module == target or module.startswith(target + "."):
                    return target
            return None

        for py in PACKAGE_ROOT.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    mods = [node.module] if node.module and not node.level else []
                elif isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                else:
                    continue
                for mod in mods:
                    hit = references_quarantined(mod or "")
                    assert hit is None, (
                        f"{py.relative_to(ROOT)} imports quarantined {hit}"
                    )


class TestImportPathsFailClosed:
    """The old import paths raise ModuleNotFoundError (no shim)."""

    @pytest.mark.parametrize("name", QUARANTINED)
    def test_quarantined_import_fails(self, name):
        proc = _in_subprocess(
            f"import importlib,sys; importlib.import_module('genesis_protocol.{name}')"
        )
        assert proc.returncode != 0, f"genesis_protocol.{name} still imports"
        assert "ModuleNotFoundError" in proc.stderr

    def test_production_entrypoints_still_import(self):
        joined = ", ".join(f"'{e}'" for e in PRODUCTION_ENTRYPOINTS)
        proc = _in_subprocess(f"import importlib; [importlib.import_module(m) for m in ({joined},)]")
        assert proc.returncode == 0, proc.stderr

    def test_no_production_entrypoint_pulls_in_quarantined_code(self):
        """Import closure of the entry points must not load a quarantined module."""
        joined = ", ".join(f"'{e}'" for e in PRODUCTION_ENTRYPOINTS)
        targets = ", ".join(f"'genesis_protocol.{n}'" for n in QUARANTINED)
        code = (
            "import importlib, sys\n"
            f"for m in ({joined},):\n"
            "    importlib.import_module(m)\n"
            f"loaded = [t for t in ({targets},) "
            "if any(k == t or k.startswith(t + '.') for k in sys.modules)]\n"
            "assert not loaded, f'production import pulled in {loaded}'\n"
        )
        proc = _in_subprocess(code)
        assert proc.returncode == 0, proc.stderr


class TestPackageDiscovery:
    """Package discovery must not see the quarantined modules."""

    def test_health_check_discovery_excludes_quarantine(self):
        """Mirror scripts/health_check.py's discovery: only genesis_protocol/*."""
        discovered = [
            entry
            for entry in sorted(os.listdir(PACKAGE_ROOT))
            if os.path.isfile(os.path.join(PACKAGE_ROOT, entry, "__init__.py"))
        ]
        for name in QUARANTINED:
            assert name not in discovered, f"discovery still lists {name}"

    def test_quarantine_tree_is_outside_package_root(self):
        assert QUARANTINE_ROOT.is_dir()
        assert PACKAGE_ROOT not in QUARANTINE_ROOT.parents
        assert not str(QUARANTINE_ROOT).startswith(str(PACKAGE_ROOT) + os.sep)

    def test_quarantine_is_not_an_installed_top_level_package(self):
        """The repo root is on sys.path, so ``import quarantine`` must not expose
        genesis_protocol.* — the inner tree is not importable by package name."""
        proc = _in_subprocess(
            "import importlib\n"
            "try:\n"
            "    importlib.import_module('quarantine.genesis_protocol.agent')\n"
            "    print('IMPORTED')\n"
            "except Exception as e:\n"
            "    print(type(e).__name__)\n"
        )
        assert "IMPORTED" not in proc.stdout, "quarantine tree is importable"


class TestProductionSurfacesIntact:
    """The move must not disturb core imports, web/Telegram, or tool policy."""

    def test_core_packages_import(self):
        proc = _in_subprocess(
            "import genesis_protocol; import genesis_protocol.updates; "
            "import genesis_protocol.integrations; import genesis_protocol.ai; "
            "import genesis_protocol.tools; import genesis_protocol.skills; "
            "import genesis_protocol.gluten; import genesis_protocol.gluten_os; "
            "import genesis_protocol.agentic; import genesis_protocol.interaction"
        )
        assert proc.returncode == 0, proc.stderr

    def test_preserved_modules_present(self):
        for rel in (
            "genesis_protocol/agentic",
            "genesis_protocol/ai",
            "genesis_protocol/tools",
            "genesis_protocol/skills",
            "genesis_protocol/gluten",
            "genesis_protocol/gluten_os",
            "genesis_protocol/integrations",
            "genesis_protocol/interaction",
            "genesis_protocol/updates/work_orders.py",
            "genesis_protocol/updates/github_prs.py",
            "genesis_v5",
        ):
            assert (ROOT / rel).exists(), f"preserved path missing: {rel}"

    def test_tool_permissions_unchanged(self):
        """The tool registry still loads with its permission policy intact."""
        proc = _in_subprocess(
            "from genesis_protocol.tools.tool_registry import (\n"
            "    get_tool_registry, ToolPermission,\n"
            ")\n"
            "r = get_tool_registry()\n"
            "tools = r.get_all_tools()\n"
            "assert tools, 'no tools registered'\n"
            "assert any(t.permission == ToolPermission.RESTRICTED for t in tools), (\n"
            "    'no restricted tool: permission policy changed'\n"
            ")\n"
        )
        assert proc.returncode == 0, proc.stderr

    def test_fail_closed_secret_gate_unchanged(self):
        """The Telegram webhook still fails closed without the shared secret."""
        proc = _in_subprocess(
            "import os\n"
            "os.environ.pop('TELEGRAM_WEBHOOK_SECRET', None)\n"
            "import web.app as appmod\n"
            "appmod.app.config['TESTING'] = True\n"
            "c = appmod.app.test_client()\n"
            "r = c.post('/api/telegram/webhook', json={'message': {'text': '/status'}})\n"
            "assert r.status_code == 401, r.status_code\n"
        )
        assert proc.returncode == 0, proc.stderr
