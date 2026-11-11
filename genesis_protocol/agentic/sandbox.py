"""Resource-bounded Python code execution for GLUTEN.

``genesis_protocol.agent`` exposes ``_run_bash(shell=True)`` with no sandbox and
no resource cap. This module is the bounded alternative: code runs in a fresh
subprocess with a hard wall-clock timeout, CPU/memory/file-size rlimits and no
inherited secrets in its environment.

The sandbox reduces blast radius; it is not a security boundary against
malicious code. Treat it as a guardrail for model-generated code, which is what
it is used for here.
"""
from __future__ import annotations

import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

# Secrets are stripped from the child environment by name. The child gets a
# minimal PATH/HOME plus any explicit ``extra_env`` the caller passes.
_SECRET_ENV_MARKERS = (
    "KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "CREDENTIAL", "API",
    "AUTH", "PRIVATE", "SESSION",
)

DEFAULT_TIMEOUT = 5.0
DEFAULT_MEMORY_MB = 256
DEFAULT_CPU_SECONDS = 5
DEFAULT_MAX_OUTPUT = 8000


@dataclass
class SandboxResult:
    """Outcome of one sandboxed execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    timed_out: bool = False
    duration_ms: int = 0
    limits: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
            "limits": self.limits,
            "error": self.error,
        }


def _scrubbed_env(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": tempfile.gettempdir(),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "PYTHONHASHSEED": "0",
    }
    for key, value in (extra_env or {}).items():
        if any(m in key.upper() for m in _SECRET_ENV_MARKERS):
            continue  # never forward anything credential-shaped
        env[key] = value
    return env


def _limit_resources(memory_mb: int, cpu_seconds: int, max_output_bytes: int):
    """Return a preexec_fn that caps the child's resources."""

    def _apply():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_FSIZE, (max_output_bytes, max_output_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        except (ValueError, OSError):
            pass  # not enforced on every platform

    return _apply


def run_python(
    code: str,
    timeout: float = DEFAULT_TIMEOUT,
    memory_mb: int = DEFAULT_MEMORY_MB,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT,
    extra_env: Optional[Dict[str, str]] = None,
    workdir: Optional[str] = None,
) -> SandboxResult:
    """Execute ``code`` in a bounded subprocess and return evidence.

    The child runs with ``-I`` (isolated: no user site-packages, no ``PYTHON*``
    env influence) in a temporary directory.
    """
    limits = {
        "timeout_s": timeout,
        "memory_mb": memory_mb,
        "cpu_seconds": cpu_seconds,
        "max_output_bytes": max_output_bytes,
    }
    python = shutil.which("python3") or sys.executable
    start = time.time()

    tmpdir = tempfile.mkdtemp(prefix="gluten_sandbox_")
    script = Path(tmpdir) / "main.py"
    script.write_text(code, encoding="utf-8")

    try:
        proc = subprocess.run(
            [python, "-I", str(script)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir or tmpdir,
            env=_scrubbed_env(extra_env),
            preexec_fn=_limit_resources(memory_mb, cpu_seconds, max_output_bytes),
        )
        duration = int((time.time() - start) * 1000)
        return SandboxResult(
            success=proc.returncode == 0,
            stdout=proc.stdout[:max_output_bytes],
            stderr=proc.stderr[:max_output_bytes],
            exit_code=proc.returncode,
            timed_out=False,
            duration_ms=duration,
            limits=limits,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.time() - start) * 1000)
        return SandboxResult(
            success=False,
            stdout=(exc.stdout or "")[:max_output_bytes] if isinstance(exc.stdout, str) else "",
            stderr=(exc.stderr or "")[:max_output_bytes] if isinstance(exc.stderr, str) else "",
            timed_out=True,
            duration_ms=duration,
            limits=limits,
            error=f"execution exceeded {timeout}s timeout",
        )
    except Exception as exc:  # pragma: no cover - defensive
        duration = int((time.time() - start) * 1000)
        return SandboxResult(
            success=False, duration_ms=duration, limits=limits, error=str(exc)
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
