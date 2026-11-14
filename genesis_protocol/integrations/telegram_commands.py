"""Extra GLUTEN commands for the Telegram/web surfaces.

These commands report *runtime* facts, not a hardcoded blurb, so the Telegram
answer matches ``/api/identity`` and ``/api/capabilities``:

* ``/capabilities`` - tools GLUTEN can actually run, with permission levels.
* ``/github``       - read-only GitHub connection status for this repository.
* ``/prs``          - open pull requests on the repository.
* ``/task <goal>``  - create a *bounded* task record (owner only). This does
  not run a long autonomous job; it records the goal in the durable task store
  so ``/task_status`` can show it, and reports the real task id.
* ``/task_status [id]`` - show a task's durable state, or list recent tasks.

Design rules match the rest of the agentic layer: fail closed, never reveal a
secret, never merge/push/deploy, and report ``UNKNOWN`` rather than guess.
``/task`` is owner-gated because it writes durable state; the read-only
commands are available to any sender the webhook already accepted.
"""
from __future__ import annotations

from typing import Any, Callable

HELP_LINES = (
    "GLUTEN commands:\n"
    "/status - runtime status (provider, tools, mode)\n"
    "/capabilities - tools GLUTEN can actually run\n"
    "/github - GitHub connection status (read-only)\n"
    "/prs - open pull requests (read-only)\n"
    "/task <goal> - record a bounded task (owner)\n"
    "/task_status [id] - task state (owner)\n"
    "/do <instruction> - order work that opens a PR (owner)\n"
    "/tasks - list work orders (owner)\n"
    "/updates - pending agent proposals (owner)\n"
    "/approve <id> - approve an update (owner)\n"
    "/reject <id> - reject an update (owner)\n"
    "/council <question> - ask several models at once\n"
    "/help - this list"
)

# Commands this module answers. ``/help`` is handled by the updates transport,
# which already owns the approval-command help; this list is only for the
# extra commands added here.
_EXTRA_VERBS = {"status", "capabilities", "github", "prs", "task", "task_status"}


def is_extra_command(text: str) -> bool:
    """True when ``text`` is one of the commands this module answers."""
    if not isinstance(text, str):
        return False
    head = text.strip().split(maxsplit=1)[0].lower()
    return head in {f"/{v}" for v in _EXTRA_VERBS}


def _verb_arg(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    verb = parts[0].lstrip("/").lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    return verb, arg


def _format_capabilities() -> str:
    """Tools GLUTEN can actually run, grouped by permission. Runtime facts."""
    from genesis_protocol.agentic.identity import describe_runtime

    runtime = describe_runtime()
    tools = runtime.get("tools") or []
    if not tools:
        return "Capabilities: UNKNOWN (tool registry not readable)"

    by_perm: dict[str, list[str]] = {}
    for tool in tools:
        by_perm.setdefault(str(tool.get("permission", "unknown")), []).append(str(tool.get("name")))

    lines = [f"GLUTEN tools: {len(tools)} registered"]
    for perm in sorted(by_perm):
        names = sorted(by_perm[perm])
        lines.append(f"  [{perm}] {', '.join(names)}")

    available = runtime.get("providers_available") or []
    unavailable = runtime.get("providers_unavailable") or []
    lines.append(f"Providers available: {', '.join(available) if available else 'none'}")
    if unavailable:
        reasons = "; ".join(f"{u.get('name')}: {u.get('reason')}" for u in unavailable)
        lines.append(f"Providers unavailable: {reasons}")
    lines.append(f"Owner configured: {runtime.get('owner_configured')}")
    lines.append(
        "Limits: code exec "
        f"{runtime.get('limits', {}).get('code_execution_timeout_s')}s, "
        f"{runtime.get('limits', {}).get('code_execution_memory_mb')}MB, "
        f"{runtime.get('limits', {}).get('code_execution_cpu_s')}s CPU"
    )
    lines.append("Restricted tools need the owner; GLUTEN cannot grant itself access.")
    return "\n".join(lines)


def _format_status() -> str:
    """Runtime status, read from the same source as /api/identity."""
    from genesis_protocol.agentic.identity import describe_runtime

    runtime = describe_runtime()
    provider = runtime.get("default_provider") or "none"
    model = runtime.get("default_model") or "unknown"
    tools = runtime.get("tools") or []
    lines = [
        "GLUTEN status: ONLINE",
        f"Provider: {provider}",
        f"Model: {model}",
        f"Tools registered: {len(tools)}",
        f"Owner configured: {runtime.get('owner_configured')}",
        "Background autonomy: OFF (no scheduler; execution is caller-driven)",
    ]
    return "\n".join(lines)


def _format_github(*, http: Callable[[str], Any] | None = None) -> str:
    from genesis_protocol.integrations.github_status import format_status, status

    return format_status(status(http=http))


def _format_prs(*, http: Callable[[str], Any] | None = None) -> str:
    from genesis_protocol.integrations.github_status import status

    data = status(http=http)
    if not data.get("connected"):
        return f"GitHub: NOT CONNECTED\nReason: {data.get('reason')}"
    if data.get("pulls_error"):
        return f"Open PRs: UNKNOWN ({data['pulls_error']})"
    pulls = data.get("pulls") or []
    if not pulls:
        return f"Open PRs: 0 on {data.get('repo')}"
    lines = [f"Open PRs: {len(pulls)} on {data.get('repo')}"]
    for p in pulls[:15]:
        mark = " (draft)" if p.get("draft") else ""
        lines.append(f"#{p.get('number')} {p.get('title')}{mark}")
    return "\n".join(lines)


def _create_task(user_id: int, goal: str) -> str:
    """Record a bounded task. Never runs an open-ended job from a chat command."""
    if not goal:
        return "Kya task banana hai? Bhejo: /task <goal>"
    from genesis_protocol.agentic.tasks import get_task_store

    store = get_task_store()
    task = store.create(int(user_id), goal[:500])
    return (
        f"Task {task.id} record ho gaya (state: {task.state}).\n"
        f"Goal: {goal[:200]}\n"
        "Ye ek bounded record hai - long autonomous job nahi chalaya. "
        "Progress: /task_status " + task.id
    )


def _task_status(user_id: int, task_id: str) -> str:
    from genesis_protocol.agentic.tasks import get_task_store

    store = get_task_store()
    if task_id:
        task = store.get(int(user_id), task_id)
        if task is None:
            return f"Task '{task_id}' nahi mila."
        lines = [f"Task {task.id} [{task.state}]", f"Goal: {task.goal}"]
        if task.steps:
            lines.append(f"Steps: {len(task.steps)}")
            for step in task.steps[-5:]:
                mark = "ok" if step.get("success") else "fail"
                lines.append(f"  #{step.get('index')} {step.get('type')} {mark}")
        else:
            lines.append("Steps: 0 (nothing executed yet)")
        return "\n".join(lines)

    tasks = store.list_tasks(int(user_id))
    if not tasks:
        return "Koi task nahi hai. Banao: /task <goal>"
    lines = [f"{len(tasks)} task(s):"]
    for task in tasks[-10:]:
        lines.append(f"  {task.id} [{task.state}] {task.goal[:60]}")
    lines.append("Detail: /task_status <id>")
    return "\n".join(lines)


def handle_extra_command(
    text: str,
    *,
    user_id: int,
    is_owner: bool,
    http: Callable[[str], Any] | None = None,
) -> str | None:
    """Answer an extra command, or return ``None`` if ``text`` is not one.

    ``is_owner`` gates the commands that write durable state (``/task``) or
    read task state (``/task_status``). The read-only informational commands
    (``/capabilities``, ``/github``, ``/prs``) are not owner-gated, matching
    the public, secret-free ``/api/identity``.
    """
    if not is_extra_command(text):
        return None
    verb, arg = _verb_arg(text)

    if verb == "status":
        # A bare /status is GLUTEN's runtime status. "/status <id>" is the
        # updates transport's update-lookup, so leave that form to it.
        if arg:
            return None
        return _format_status()
    if verb == "capabilities":
        return _format_capabilities()
    if verb == "github":
        return _format_github(http=http)
    if verb == "prs":
        return _format_prs(http=http)

    # Task commands write/read per-user durable state: owner only, fail closed.
    if verb in {"task", "task_status"}:
        if not is_owner:
            return "Ye command sirf owner ke liye hai."
        if verb == "task":
            return _create_task(user_id, arg)
        return _task_status(user_id, arg)

    return None
