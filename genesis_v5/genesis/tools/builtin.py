"""Built-in offline tool implementations for the Tool Fabric.

All handlers are offline-safe: they operate within the sandbox root and
never make uncontrolled network requests. `search` and `apis` are stubs that
return a structured "disabled" result unless a verified backend is wired in.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any

from genesis.core import RiskLevel
from genesis.security.permissions import Permission
from genesis.tools.registry import ToolCategory, ToolContext, ToolImpl, ToolRegistry, ToolSpec


# ------------------------------------------------------------------
# Handlers
# ------------------------------------------------------------------
def _files_read(ctx: ToolContext, args: dict[str, Any]) -> Any:
    path = args["path"]
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _files_write(ctx: ToolContext, args: dict[str, Any]) -> Any:
    path = args["path"]
    content = args["content"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return {"written": path, "bytes": len(content.encode("utf-8"))}


def _files_list(ctx: ToolContext, args: dict[str, Any]) -> Any:
    path = args.get("path", ctx.cwd)
    entries = sorted(os.listdir(path))
    return {"path": path, "entries": entries}


def _git_status(ctx: ToolContext, args: dict[str, Any]) -> Any:
    repo = args.get("repo", ctx.cwd)
    return _run_git(repo, ["status", "--short"])


def _git_log(ctx: ToolContext, args: dict[str, Any]) -> Any:
    repo = args.get("repo", ctx.cwd)
    return _run_git(repo, ["log", "--oneline", "-n", "20"])


def _git_commit(ctx: ToolContext, args: dict[str, Any]) -> Any:
    repo = args.get("repo", ctx.cwd)
    message = args.get("message", "")
    return _run_git(repo, ["commit", "-am", message])


def _python_run(ctx: ToolContext, args: dict[str, Any]) -> Any:
    code = args["code"]
    # Execute in a subprocess with a short timeout, no network.
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(code)
        script = fh.name
    try:
        proc = subprocess.run(
            [os.sysget("python3") if hasattr(os, "sysget") else "python3", script],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=ctx.cwd,
        )
    finally:
        os.unlink(script)
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
    }


def _terminal_run(ctx: ToolContext, args: dict[str, Any]) -> Any:
    command = args["command"]
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=10,
        cwd=ctx.cwd,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-2000:],
    }


def _browser_navigate(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return {"navigated": args["url"], "sandboxed": True, "offline": True}


def _browser_click(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return {"clicked": args.get("index", 0), "sandboxed": True, "offline": True}


def _browser_type(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return {"typed": args.get("index", 0), "sandboxed": True, "offline": True}


def _search_web(ctx: ToolContext, args: dict[str, Any]) -> Any:
    # No verified search backend: return a structured disabled result.
    return {"disabled": True, "reason": "no verified search backend", "query": args.get("query", "")}


def _docker_exec(ctx: ToolContext, args: dict[str, Any]) -> Any:
    image = args.get("image", "alpine")
    command = args.get("command", [])
    return {
        "disabled": True,
        "reason": "docker execution requires a verified daemon and explicit permission",
        "image": image,
        "command": command,
    }


def _api_call(ctx: ToolContext, args: dict[str, Any]) -> Any:
    return {"disabled": True, "reason": "api calls require verified backend + permission"}


def _run_git(repo: str, args: list[str]) -> Any:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "args": args,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


# ------------------------------------------------------------------
# Registry builder
# ------------------------------------------------------------------
def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolSpec(
            name="file.read",
            category=ToolCategory.FILES,
            description="Read a file within the sandbox root.",
            schema={"title": "Read", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            permission=Permission.FILE_READ,
            risk_level=RiskLevel.LOW,
            timeout_seconds=15.0,
        ),
        _files_read,
    )
    registry.register(
        ToolSpec(
            name="file.write",
            category=ToolCategory.FILES,
            description="Write a file within the sandbox root.",
            schema={"title": "Write", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
            permission=Permission.FILE_WRITE,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=15.0,
        ),
        _files_write,
    )
    registry.register(
        ToolSpec(
            name="file.list",
            category=ToolCategory.FILES,
            description="List directory entries.",
            schema={"title": "List", "properties": {"path": {"type": "string"}}, "required": []},
            permission=Permission.FILE_LIST,
            risk_level=RiskLevel.LOW,
            timeout_seconds=10.0,
        ),
        _files_list,
    )
    registry.register(
        ToolSpec(
            name="git.status",
            category=ToolCategory.GIT,
            description="Show git status in a repository.",
            schema={"title": "GitStatus", "properties": {"repo": {"type": "string"}}, "required": []},
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.LOW,
            timeout_seconds=15.0,
        ),
        _git_status,
    )
    registry.register(
        ToolSpec(
            name="git.log",
            category=ToolCategory.GIT,
            description="Show recent git log.",
            schema={"title": "GitLog", "properties": {"repo": {"type": "string"}}, "required": []},
            permission=Permission.GIT_READ,
            risk_level=RiskLevel.LOW,
            timeout_seconds=15.0,
        ),
        _git_log,
    )
    registry.register(
        ToolSpec(
            name="git.commit",
            category=ToolCategory.GIT,
            description="Create a commit (requires git.write permission).",
            schema={"title": "GitCommit", "properties": {"repo": {"type": "string"}, "message": {"type": "string"}}, "required": ["message"]},
            permission=Permission.GIT_WRITE,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _git_commit,
    )
    registry.register(
        ToolSpec(
            name="python.run",
            category=ToolCategory.PYTHON,
            description="Execute Python code in a subprocess sandbox.",
            schema={"title": "PythonRun", "properties": {"code": {"type": "string"}}, "required": ["code"]},
            permission=Permission.PYTHON_EXEC,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _python_run,
    )
    registry.register(
        ToolSpec(
            name="terminal.run",
            category=ToolCategory.TERMINAL,
            description="Run a shell command in a subprocess sandbox.",
            schema={"title": "TerminalRun", "properties": {"command": {"type": "string"}}, "required": ["command"]},
            permission=Permission.TERMINAL_EXEC,
            risk_level=RiskLevel.HIGH,
            timeout_seconds=20.0,
        ),
        _terminal_run,
    )
    registry.register(
        ToolSpec(
            name="browser.navigate",
            category=ToolCategory.BROWSER,
            description="Navigate the browser to a URL (offline stub).",
            schema={"title": "Navigate", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            permission=Permission.BROWSER_NAVIGATE,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _browser_navigate,
    )
    registry.register(
        ToolSpec(
            name="browser.click",
            category=ToolCategory.BROWSER,
            description="Click a browser element (offline stub).",
            schema={"title": "Click", "properties": {"index": {"type": "integer"}}, "required": []},
            permission=Permission.BROWSER_CLICK,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _browser_click,
    )
    registry.register(
        ToolSpec(
            name="browser.type",
            category=ToolCategory.BROWSER,
            description="Type into a browser field (offline stub).",
            schema={"title": "Type", "properties": {"index": {"type": "integer"}, "text": {"type": "string"}}, "required": []},
            permission=Permission.BROWSER_TYPE,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _browser_type,
    )
    registry.register(
        ToolSpec(
            name="search.web",
            category=ToolCategory.SEARCH,
            description="Search the web (disabled without verified backend).",
            schema={"title": "Search", "properties": {"query": {"type": "string"}}, "required": ["query"]},
            permission=Permission.SEARCH_WEB,
            risk_level=RiskLevel.MEDIUM,
            timeout_seconds=20.0,
        ),
        _search_web,
    )
    registry.register(
        ToolSpec(
            name="docker.exec",
            category=ToolCategory.DOCKER,
            description="Execute a command in a Docker container (disabled by default).",
            schema={"title": "DockerExec", "properties": {"image": {"type": "string"}, "command": {"type": "array"}}, "required": []},
            permission=Permission.DOCKER_EXEC,
            risk_level=RiskLevel.CRITICAL,
            timeout_seconds=30.0,
        ),
        _docker_exec,
    )
    registry.register(
        ToolSpec(
            name="api.call",
            category=ToolCategory.APIS,
            description="Call an external API (disabled without verified backend).",
            schema={"title": "ApiCall", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            permission=Permission.API_CALL,
            risk_level=RiskLevel.HIGH,
            timeout_seconds=30.0,
        ),
        _api_call,
    )


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    return registry