"""Owner work orders — the ``/do`` command.

Genesis is not a chatbot: the owner gives one order and the agent does the
work. ``/do <instruction>`` parks an order; the self-improvement harness picks
it up, runs an OpenHands conversation against the repository, and opens a pull
request. Nothing merges without the owner's ``/approve`` — the same human gate
as the automatic cycles.

This module is the transport-agnostic half (grammar + rendering), stdlib-only,
so the runner can import it without the rest of the app.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkOrder:
    """One instruction the owner asked Genesis to carry out."""

    id: str
    instruction: str
    state: str = "queued"  # queued | running | done | failed | cancelled
    pr: str = ""
    note: str = ""
    created: str = ""
    history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "instruction": self.instruction,
            "state": self.state,
            "pr": self.pr,
            "note": self.note,
            "created": self.created,
        }


_WORK_RE = re.compile(r"^/(?P<verb>do|cancel)\b\s*(?P<arg>.*)$", re.IGNORECASE)
_TASKS_RE = re.compile(r"^/tasks\b", re.IGNORECASE)

WORK_HELP = (
    "Genesis work orders:\n"
    "/do <instruction> — order Genesis to do something (it opens a PR for your approval)\n"
    "/tasks — list your work orders\n"
    "/cancel <id> — cancel a work order\n"
    "Nothing merges without /approve."
)


def parse_work_order(text: str) -> tuple[str, str] | None:
    """Return (verb, arg) for ``/do`` or ``/cancel``, else None."""
    if not isinstance(text, str):
        return None
    match = _WORK_RE.match(text.strip())
    if not match:
        return None
    return match.group("verb").lower(), match.group("arg").strip()


def is_tasks_command(text: str) -> bool:
    return isinstance(text, str) and bool(_TASKS_RE.match(text.strip()))


def render_work_orders(orders: list[WorkOrder]) -> str:
    if not orders:
        return "Koi work order nahi hai. Naya order: /do <instruction>"
    icon = {"queued": "🕓", "running": "⚙️", "done": "✅", "failed": "❌", "cancelled": "🚫"}
    lines = [f"{len(orders)} work order(s):"]
    for order in orders:
        mark = icon.get(order.state, "•")
        extra = f" — {order.pr}" if order.pr else (f" — {order.note}" if order.note else "")
        lines.append(f"{mark} #{order.id} [{order.state}] {order.instruction[:60]}{extra}")
    return "\n".join(lines)


def resolve_order(orders: list[WorkOrder], token: str) -> WorkOrder | None:
    """Resolve a token to an order: exact id, id-prefix, or 1-based index."""
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        index = int(token)
        if 1 <= index <= len(orders):
            return orders[index - 1]
    for order in orders:
        if order.id == token:
            return order
    matches = [order for order in orders if order.id.startswith(token)]
    return matches[0] if len(matches) == 1 else None
