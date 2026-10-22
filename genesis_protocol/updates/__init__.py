"""Human-approved update pipeline.

Genesis proposes; a human approves; only then does it push and deploy.

The proposal an agent produces is a pull request (branch + diff). A PR is inert
until it is merged, and this layer is the only thing allowed to merge one — and
only in response to an explicit ``/approve`` from the owner. Merging is what
pushes to ``main`` and, through ``deploy-space.yml``, deploys to the HF Space.

This module holds the transport-agnostic half: the command grammar and the
rendering. ``GitHubPRTransport`` (in ``github_prs``) is the production
transport; tests use a fake transport. Nothing here does network I/O.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Update:
    """One pending change awaiting the owner's decision."""

    id: str
    title: str
    branch: str = ""
    url: str = ""
    area: str = ""
    priority: float = 0.5
    state: str = "proposed"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "branch": self.branch,
            "url": self.url,
            "area": self.area,
            "priority": round(self.priority, 4),
            "state": self.state,
            "notes": list(self.notes),
        }


class UpdateTransport(Protocol):
    """What a transport must provide so the owner can approve an update."""

    def list_open(self) -> list[Update]:
        ...

    def approve(self, token: str, reason: str = "") -> str:
        """Approve and land the update. Returns a human-readable result."""

    def reject(self, token: str, reason: str = "") -> str:
        ...

    def status(self, token: str) -> str:
        ...


_COMMAND_RE = re.compile(
    r"^/(?P<verb>approve|reject|list|updates|pending|status|help)\b\s*(?P<arg>.*)$",
    re.IGNORECASE,
)

HELP_TEXT = (
    "Genesis update commands:\n"
    "/updates — list pending updates\n"
    "/approve <id|number> — approve, push and deploy an update\n"
    "/reject <id|number> [reason] — reject an update\n"
    "/status <id> — show one update"
)


def parse_command(text: str) -> tuple[str, str] | None:
    """Return (verb, arg) for a recognised command, else None."""
    if not isinstance(text, str):
        return None
    match = _COMMAND_RE.match(text.strip())
    if not match:
        return None
    return match.group("verb").lower(), match.group("arg").strip()


def render_list(items: list[Update]) -> str:
    if not items:
        return "Koi pending update nahi hai."
    lines = [f"{len(items)} pending update(s):"]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. #{item.id}  [{item.priority:.2f}] {item.title}")
    lines.append("")
    lines.append("Approve: /approve <id|number>   Reject: /reject <id|number>")
    return "\n".join(lines)


def resolve(items: list[Update], token: str) -> Update | None:
    """Resolve a token to an open update: id, id-prefix, or 1-based index."""
    token = (token or "").strip()
    if not token:
        return None
    if token.isdigit():
        index = int(token)
        if 1 <= index <= len(items):
            return items[index - 1]
        # Fall through: a numeric token may still be an exact id.
    for item in items:
        if item.id == token:
            return item
    matches = [item for item in items if item.id.startswith(token)]
    return matches[0] if len(matches) == 1 else None


def newest(items: list[Update]) -> Update | None:
    """The most recently opened update (highest PR number).

    A bare ``/approve`` — e.g. a Telegram client that sends only ``/approve``
    when the owner taps the command text in a notification — means "the newest
    one". Picking by PR number (not list order) keeps that deterministic.
    """
    if not items:
        return None
    numeric = [item for item in items if str(item.id).isdigit()]
    if numeric:
        return max(numeric, key=lambda item: int(item.id))
    return items[0]


def handle_command(text: str, transport: UpdateTransport) -> str | None:
    """Handle an approval command and return the reply text, or None.

    ``None`` means "not one of my commands" — the caller falls through to its
    normal handling. A recognised command always returns a string.
    """
    parsed = parse_command(text)
    if parsed is None:
        return None
    verb, arg = parsed

    if verb in {"list", "updates", "pending"}:
        return render_list(transport.list_open())
    if verb == "help":
        return HELP_TEXT
    if verb == "status":
        return "Use: /status <id>" if not arg else transport.status(arg)

    if verb in {"approve", "reject"}:
        action = transport.approve if verb == "approve" else transport.reject
        if not arg:
            # A bare /approve or /reject targets the newest pending update, so
            # tapping the command in a notification still does the right thing.
            target = newest(transport.list_open())
            if target is None:
                return "Koi pending update nahi hai."
            try:
                return f"Newest pending: #{target.id}\n{action(target.id, '')}"
            except Exception as exc:  # noqa: BLE001 - a failed action is reported, not hidden
                return f"⚠️ {exc}"
        token, _, reason = arg.partition(" ")
        try:
            return action(token.strip(), reason.strip())
        except Exception as exc:  # noqa: BLE001 - a failed action is reported, not hidden
            return f"⚠️ {exc}"
    return None
