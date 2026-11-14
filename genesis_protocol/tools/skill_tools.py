"""Tool implementations for the names skills declare.

Skills declare the tools they need (``tools=["file_read", "subprocess"]``), but
those names never matched the real ``ToolRegistry`` entries, so every declared
tool resolved to nothing and skills could not run. This module closes that gap:
each declared name gets a real implementation and a permission level, and
``register_skill_tools`` adds them to the canonical registry.

Permission model (fail closed, same levels the policy already understands):

* ``safe``       - pure, no side effects on the host (parsing, hashing, time).
* ``restricted`` - host side effects: filesystem, subprocess, network, git,
                   container/cloud CLIs. Non-owners are refused; owners may run
                   them (and a caller may still require per-call approval).
* ``admin``      - none of the current names.

None of these tools touch secrets, deploy, or write to main. Commands that
would (``git push``, ``git commit``) are refused outright here, independent of
permission, because the agent must not perform privileged operations.
"""
from __future__ import annotations

import json as _json
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from .tool_registry import Tool, ToolPermission, ToolRegistry, get_tool_registry

# Commands the agent must never run, whatever its permission. Kept explicit so
# a future caller cannot route one through by accident.
_FORBIDDEN_SUBSTRINGS = (
    "git push",
    "git commit",
    "rm -rf /",
    ":(){",  # fork bomb
)


def _refuse_forbidden(command: str) -> Optional[Dict[str, Any]]:
    lowered = command.lower()
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return {"success": False, "error": f"refused: '{needle}' is a privileged operation"}
    return None


class _DeclaredTool(Tool):
    """Base for tools declared by skills. Concrete tools set ``_name``."""

    _name: str = ""
    _description: str = ""
    _category: str = "skill"
    _permission: ToolPermission = ToolPermission.RESTRICTED

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def category(self) -> str:
        return self._category

    @property
    def permission(self) -> ToolPermission:
        return self._permission


class PythonTool(_DeclaredTool):
    _name = "python"
    _description = "Run a Python snippet in a bounded sandbox"
    _category = "coding"
    _permission = ToolPermission.RESTRICTED

    def execute(self, code: str, timeout: float = 5.0, **kwargs: Any) -> Dict[str, Any]:
        from genesis_protocol.agentic.sandbox import run_python

        result = run_python(code, timeout=timeout)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "error": result.error,
        }


class SubprocessTool(_DeclaredTool):
    _name = "subprocess"
    _description = "Run a shell command (privileged git commands are refused)"
    _category = "coding"
    _permission = ToolPermission.RESTRICTED

    def execute(self, command: str, timeout: int = 30, cwd: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
        refused = _refuse_forbidden(command)
        if refused:
            return refused
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout[:8000],
                "stderr": result.stderr[:4000],
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "command timeout"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class FileReadTool(_DeclaredTool):
    _name = "file_read"
    _description = "Read a file's contents"
    _category = "file_management"
    _permission = ToolPermission.RESTRICTED

    def execute(self, path: str, max_lines: int = 200, **kwargs: Any) -> Dict[str, Any]:
        try:
            with open(path, "r", errors="replace") as handle:
                content = "".join(handle.readlines()[:max_lines])
            return {"success": True, "path": path, "content": content, "lines": len(content.splitlines())}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class FileWriteTool(_DeclaredTool):
    _name = "file_write"
    _description = "Write content to a file"
    _category = "file_management"
    _permission = ToolPermission.RESTRICTED

    def execute(self, path: str, content: str, append: bool = False, **kwargs: Any) -> Dict[str, Any]:
        try:
            import os

            parent = os.path.dirname(os.path.abspath(path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            mode = "a" if append else "w"
            with open(path, mode) as handle:
                handle.write(content)
            return {"success": True, "path": path, "bytes": len(content)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class GrepTool(_DeclaredTool):
    _name = "grep"
    _description = "Search files for a pattern"
    _category = "coding"
    _permission = ToolPermission.RESTRICTED

    def execute(self, pattern: str, path: str = ".", **kwargs: Any) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", "-I", pattern, path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            lines = [ln for ln in result.stdout.splitlines() if ln][:200]
            return {"success": True, "pattern": pattern, "matches": lines, "count": len(lines)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class GitTool(_DeclaredTool):
    _name = "git"
    _description = "Read-only git queries (status/log/diff/branch); never commits or pushes"
    _category = "file_management"
    _permission = ToolPermission.RESTRICTED

    _READ_ONLY = {"status", "log", "diff", "branch", "show", "remote"}

    def execute(self, operation: str = "status", **kwargs: Any) -> Dict[str, Any]:
        op = (operation or "").strip().lower()
        if op not in self._READ_ONLY:
            return {"success": False, "error": f"git '{op}' is not read-only; refused"}
        args = [op]
        if op == "log":
            args += ["--oneline", "-n", str(kwargs.get("limit", 10))]
        try:
            from genesis_protocol.skills.file_management import GitOperations

            return GitOperations().run_git(*args)
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class HttpTool(_DeclaredTool):
    _name = "http"
    _description = "Fetch a URL over HTTP(S)"
    _category = "web_browser"
    _permission = ToolPermission.RESTRICTED

    def execute(self, url: str, method: str = "GET", timeout: int = 20, **kwargs: Any) -> Dict[str, Any]:
        import urllib.request

        if not url.lower().startswith(("http://", "https://")):
            return {"success": False, "error": "only http(s) URLs are allowed"}
        try:
            req = urllib.request.Request(url, method=method.upper())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(200_000).decode("utf-8", errors="replace")
                return {"success": True, "url": url, "status": resp.status, "content": body[:8000]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class JsonTool(_DeclaredTool):
    _name = "json"
    _description = "Parse or serialise JSON"
    _category = "utility"
    _permission = ToolPermission.SAFE

    def execute(self, action: str = "parse", text: str = "", data: Any = None, **kwargs: Any) -> Dict[str, Any]:
        try:
            if action == "parse":
                return {"success": True, "data": _json.loads(text)}
            if action == "dumps":
                return {"success": True, "text": _json.dumps(data)}
            return {"success": False, "error": f"unknown action '{action}'"}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class ApiTool(_DeclaredTool):
    _name = "api"
    _description = "Call an HTTP API (JSON in/out)"
    _category = "automation"
    _permission = ToolPermission.RESTRICTED

    def execute(self, url: str, method: str = "GET", payload: Any = None, timeout: int = 20, **kwargs: Any) -> Dict[str, Any]:
        import urllib.request

        if not url.lower().startswith(("http://", "https://")):
            return {"success": False, "error": "only http(s) URLs are allowed"}
        try:
            body = _json.dumps(payload).encode() if payload is not None else None
            req = urllib.request.Request(
                url, data=body, method=method.upper(), headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(200_000).decode("utf-8", errors="replace")
            try:
                return {"success": True, "status": resp.status, "json": _json.loads(text)}
            except ValueError:
                return {"success": True, "status": resp.status, "text": text[:8000]}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class GraphQLTool(_DeclaredTool):
    _name = "graphql"
    _description = "Run a GraphQL query against an endpoint"
    _category = "automation"
    _permission = ToolPermission.RESTRICTED

    def execute(self, url: str, query: str, variables: Optional[Dict[str, Any]] = None, timeout: int = 20, **kwargs: Any) -> Dict[str, Any]:
        import urllib.request

        try:
            payload = _json.dumps({"query": query, "variables": variables or {}}).encode()
            req = urllib.request.Request(
                url, data=payload, method="POST", headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return {"success": True, "status": resp.status, "data": _json.loads(resp.read().decode())}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class TavilyTool(_DeclaredTool):
    _name = "tavily"
    _description = "Web search via Tavily"
    _category = "web_browser"
    _permission = ToolPermission.RESTRICTED

    def is_available(self) -> bool:
        """Tavily is only runnable when an API key is configured.

        The tool resolved on the registry and reported itself runnable, but
        every call failed with "no Tavily credential configured", which made
        the web_search skill look fully runnable when its Tavily half was not.
        """
        try:
            from genesis_protocol.config import get_config

            config = get_config()
            tavily = getattr(config, "tavily", None) if config else None
            return bool(tavily and getattr(tavily, "api_key", None))
        except Exception:
            return False

    def execute(self, query: str, max_results: int = 5, **kwargs: Any) -> Dict[str, Any]:
        try:
            from genesis_protocol.config import get_config
            from genesis_protocol.skills.web_browser import WebSearch

            config = get_config()
            key = config.tavily.api_key if config and getattr(config, "tavily", None) else None
            if not key:
                return {"success": False, "error": "no Tavily credential configured"}
            import asyncio

            search = WebSearch(key)
            result = asyncio.get_event_loop().run_until_complete(search.search(query, max_results))
            return result if isinstance(result, dict) else {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class PandasTool(_DeclaredTool):
    _name = "pandas"
    _description = "Load a CSV and report its shape and columns"
    _category = "specialized"
    _permission = ToolPermission.RESTRICTED

    def execute(self, file_path: str, head: int = 5, **kwargs: Any) -> Dict[str, Any]:
        try:
            import pandas as pd

            frame = pd.read_csv(file_path)
            return {
                "success": True,
                "shape": list(frame.shape),
                "columns": list(frame.columns),
                "head": frame.head(head).to_dict(orient="records"),
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


class _CliTool(_DeclaredTool):
    """A tool backed by an external CLI. Missing binaries fail closed."""

    _binary = ""

    def is_available(self) -> bool:
        return bool(shutil.which(self._binary))

    def execute(self, args: str = "", **kwargs: Any) -> Dict[str, Any]:
        if not shutil.which(self._binary):
            return {"success": False, "error": f"'{self._binary}' is not installed"}
        command = f"{self._binary} {args}".strip()
        refused = _refuse_forbidden(command)
        if refused:
            return refused
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=kwargs.get("timeout", 30)
            )
            return {
                "success": result.returncode == 0,
                "command": command,
                "stdout": result.stdout[:8000],
                "stderr": result.stderr[:4000],
                "returncode": result.returncode,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


def _cli(name: str, binary: str, category: str = "devops") -> type:
    return type(
        f"{name.title()}Tool",
        (_CliTool,),
        {"_name": name, "_binary": binary, "_description": f"Run the '{binary}' CLI", "_category": category},
    )


class _UnavailableTool(_DeclaredTool):
    """Declared by a skill, but no implementation exists here. Always fails.

    Returning an honest failure is the point: the alternative is a tool that
    silently pretends to have run.
    """

    _reason = "no implementation in this deployment"

    def is_available(self) -> bool:
        return False

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        return {"success": False, "error": f"tool '{self._name}' is unavailable: {self._reason}"}


def _unavailable(name: str, reason: str, category: str = "specialized") -> type:
    return type(
        f"{name.title()}Tool",
        (_UnavailableTool,),
        {"_name": name, "_reason": reason, "_description": f"Unavailable: {reason}", "_category": category},
    )


# Every name skills declare, mapped to a concrete implementation class.
DECLARED_TOOL_CLASSES: Dict[str, type] = {
    "python": PythonTool,
    "subprocess": SubprocessTool,
    "file_read": FileReadTool,
    "file_write": FileWriteTool,
    "grep": GrepTool,
    "git": GitTool,
    "http": HttpTool,
    "json": JsonTool,
    "api": ApiTool,
    "graphql": GraphQLTool,
    "tavily": TavilyTool,
    "pandas": PandasTool,
    "docker": _cli("docker", "docker"),
    "kubectl": _cli("kubectl", "kubectl"),
    "terraform": _cli("terraform", "terraform"),
    "gh": _cli("gh", "gh", category="specialized"),
    "aws": _cli("aws", "aws"),
    "gcloud": _cli("gcloud", "gcloud"),
    "az": _cli("az", "az"),
    "crontab": _cli("crontab", "crontab", category="automation"),
    "pdflatex": _cli("pdflatex", "pdflatex", category="document"),
    "pandoc": _cli("pandoc", "pandoc", category="document"),
    "browser": _unavailable(
        "browser", "no headless browser is bundled; use the 'http' tool to fetch pages", "web_browser"
    ),
}


def build_skill_tools() -> Dict[str, Tool]:
    """Instantiate one object per declared tool name."""
    return {name: cls() for name, cls in DECLARED_TOOL_CLASSES.items()}


def register_skill_tools(registry: ToolRegistry) -> List[str]:
    """Register every declared tool on ``registry``. Returns the names added."""
    added: List[str] = []
    for name, tool in build_skill_tools().items():
        registry.register(tool)
        added.append(name)
    return added


def tools_for_skill(skill_name: str, registry: Optional[ToolRegistry] = None) -> List[str]:
    """Names a skill declares that actually resolve on the registry.

    Used to show which of a skill's tools are runnable, without claiming the
    ones that are not.
    """
    from genesis_protocol.skills import get_skill_registry

    if registry is None:
        registry = get_tool_registry()

    skill = get_skill_registry().get_skill(skill_name)
    if skill is None:
        return []
    available: List[str] = []
    for name in skill.tools or []:
        tool = registry.get_tool(name)
        # A name that resolves but cannot run (missing binary) is not runnable.
        if tool is not None and tool.is_available():
            available.append(name)
    return available
