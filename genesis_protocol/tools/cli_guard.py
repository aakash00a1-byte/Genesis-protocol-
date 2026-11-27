"""The one place a CLI command may be executed from.

``shell=False`` removes shell injection; it says nothing about what the tool is
allowed to *do*, and it never helped a module that builds its own argv. So every
CLI call in the product goes through ``run_guarded_command``:

1. ``cli_policy.classify`` decides (credential noun -> deny, read verb -> allow,
   dangerous verb -> deny, otherwise consent);
2. the caller must be the verified owner - no identity is refused, so a skill or
   a direct import cannot run a command;
3. a non-read-only command claims a single-use approval bound to
   ``canonical_command(binary, argv)``, so a different argument or a replay is
   refused;
4. the child runs with ``shell=False`` and a scrubbed environment.

``probe`` is the only self-directed call and only accepts fixed ``--version``
arguments. Do not add a ``subprocess`` call anywhere else in the product;
``tests/test_cli_gate_skills.py`` enforces that.
"""
from __future__ import annotations

import subprocess
from collections.abc import Sequence
from typing import Any

# Availability checks are the only commands that may run without a caller:
# fixed arguments, no user input.
PROBE_ARGS = {("--version",), ("version", "--client")}


def scrubbed_env() -> dict[str, str]:
    """The child gets no inherited credential, matching the code sandbox."""
    from genesis_protocol.agentic.sandbox import _scrubbed_env as sandbox_env

    return sandbox_env()


def probe(binary: str, args: Sequence[str]) -> bool:
    """True when ``binary`` answers a fixed version probe."""
    if tuple(args) not in PROBE_ARGS:
        return False
    try:
        subprocess.run([binary, *args], capture_output=True, timeout=5,
                       shell=False, env=scrubbed_env())
        return True
    except Exception:
        return False


def run_guarded_command(
    binary: str,
    args: Sequence[str],
    *,
    user_id: int | None = None,
    approval_id: str | None = None,
    timeout: int = 60,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run one CLI command, or refuse it and say why."""
    from genesis_protocol.tools.cli_policy import canonical_command, classify

    argv: list[str] = [str(a) for a in args]
    command = " ".join([binary, *argv])
    verdict = classify(binary, argv)

    def refuse(reason: str) -> dict[str, Any]:
        return {"success": False, "denied": True, "operation": verdict.operation,
                "command": command, "error": reason}

    if verdict.denied:
        return refuse(f"refused: {verdict.reason}")

    from genesis_protocol.agentic.policy import get_agent_policy

    if user_id is None:
        return refuse("refused: this command requires the owner and no caller "
                      "identity was supplied")
    if not get_agent_policy().is_owner(int(user_id)):
        return refuse(f"refused: user {user_id} is not the owner")

    if verdict.needs_consent:
        if not approval_id:
            return refuse("refused: an approval record is required for this "
                          "operation (approval_id) and nothing was run")
        from genesis_protocol.agentic.code_consent import get_code_consent

        approved, reason = get_code_consent().claim(
            int(user_id), str(approval_id), canonical_command(binary, argv))
        if approved is None:
            return refuse(f"refused: {reason}")

    try:
        result = subprocess.run(
            [binary, *argv], capture_output=True, text=True, timeout=timeout,
            shell=False, env=scrubbed_env(), cwd=cwd,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
