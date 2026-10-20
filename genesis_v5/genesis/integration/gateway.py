"""The chat gateway: from a chat message to a governed action.

This is the one place a chat platform meets the Kernel. It is deliberately
thin and paranoid:

  * the channel must be allow-listed, and the sender is rate-limited;
  * the message text is scanned by ``TaskGuard`` for forbidden actions and
    prompt injection before anything runs;
  * the text is parsed into a *command*, never executed as code;
  * ``/task`` runs the bounded autonomy loop; ``/generate`` runs the
    side-effect-free generation pipeline; ``/submit`` offers tool requests to
    the authority gate. Nothing here reaches a tool directly.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from genesis.autonomy.guard import TaskGuard
from genesis.config.settings import IntegrationConfig
from genesis.security.ratelimit import RateLimiter
from genesis.tools.gateway import ToolRequest


@dataclass
class ChatCommand:
    """A parsed chat command. ``name`` is one of generate/task/submit/help."""

    name: str
    argument: str = ""
    requests: list[dict[str, Any]] = field(default_factory=list)
    raw: str = ""


@dataclass
class ChatReply:
    ok: bool
    text: str
    command: str = ""
    details: dict[str, Any] = field(default_factory=dict)


def parse_command(text: str) -> ChatCommand:
    """Parse a chat message into a command. Unknown text becomes /help."""
    stripped = (text or "").strip()
    if not stripped:
        return ChatCommand(name="help", raw=text)
    if not stripped.startswith("/"):
        return ChatCommand(name="help", argument=stripped, raw=text)
    head, _, rest = stripped.partition(" ")
    name = head[1:].strip().lower()
    rest = rest.strip()
    if name in {"generate", "gen"}:
        return ChatCommand(name="generate", argument=rest, raw=text)
    if name in {"task", "run", "autonomy"}:
        return ChatCommand(name="task", argument=rest, raw=text)
    if name in {"submit"}:
        return ChatCommand(name="submit", argument=rest, raw=text)
    return ChatCommand(name="help", argument=rest, raw=text)


class ChatGateway:
    """Turn an allow-listed chat message into a governed Kernel call."""

    def __init__(
        self,
        *,
        config: IntegrationConfig,
        service: Any,
        loop: Any = None,
        guard: TaskGuard | None = None,
        limiter: RateLimiter | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config
        self.service = service
        self.loop = loop
        self.guard = guard or TaskGuard()
        self.limiter = limiter or RateLimiter(
            limit_per_minute=config.rate_limit_per_minute
        )

    # ------------------------------------------------------------------
    def handle(
        self,
        *,
        channel: str,
        sender: str,
        text: str,
    ) -> ChatReply:
        if not self._allowed(channel):
            return ChatReply(
                ok=False,
                text="this channel is not authorised to talk to Genesis",
                details={"reason": "channel_not_allowed", "channel": channel},
            )
        if not self.limiter.allow(sender):
            return ChatReply(
                ok=False,
                text="rate limit reached; please slow down",
                details={"reason": "rate_limited", "sender": sender},
            )

        decision = self.guard.scan_text(text)
        if not decision.allowed:
            return ChatReply(
                ok=False,
                text=f"refused: {decision.reason}",
                details={"reason": decision.reason, "matched": decision.matched},
            )

        command = parse_command(text)
        if command.name == "generate":
            return self._generate(command)
        if command.name == "task":
            return self._task(command)
        if command.name == "submit":
            return self._submit(command)
        return self._help()

    # ------------------------------------------------------------------
    def _allowed(self, channel: str) -> bool:
        if not self.config.allowed_channels:
            return False
        return channel in self.config.allowed_channels

    def _generate(self, command: ChatCommand) -> ChatReply:
        if not command.argument:
            return ChatReply(ok=False, text="usage: /generate <input>")
        result = self.service.generate(
            command.argument, shots=self.config.shots
        )
        return ChatReply(
            ok=True,
            text=f"generated {len(result.get('generation', {}).get('branches', []))} "
            f"proposal(s)",
            command="generate",
            details=result,
        )

    def _task(self, command: ChatCommand) -> ChatReply:
        if not command.argument:
            return ChatReply(ok=False, text="usage: /task <task>")
        if self.loop is None:
            return ChatReply(
                ok=False,
                text="autonomy loop is not wired; /task is unavailable",
                details={"reason": "loop_not_wired"},
            )
        result = self.loop.run(
            command.argument, actor="chat", role=self.config.default_role
        )
        return ChatReply(
            ok=bool(getattr(result, "ok", False)),
            text=f"task {result.status.value}: {result.result or '(no result)'}",
            command="task",
            details=result.to_dict(),
        )

    def _submit(self, command: ChatCommand) -> ChatReply:
        if not command.argument:
            return ChatReply(ok=False, text="usage: /submit <input>")
        # A chat message may not smuggle a tool request; the only requests
        # offered are ones the gateway builds itself. Here that is none — the
        # /submit path exists so a future, explicit request list can be gated.
        requests: list[dict[str, Any]] = list(command.requests)
        result = self.service.submit(command.argument, requests)
        return ChatReply(
            ok=True,
            text=f"executed={result.get('executed', 0)} denied={result.get('denied', 0)}",
            command="submit",
            details=result,
        )

    def _help(self) -> ChatReply:
        return ChatReply(
            ok=True,
            text=(
                "commands: /generate <input> (proposals) · "
                "/task <task> (bounded autonomous run) · "
                "/submit <input> (governed tool requests)"
            ),
            command="help",
        )


def to_tool_requests(payloads: list[dict[str, Any]]) -> list[ToolRequest]:
    """Build ToolRequests from raw payloads. Kept explicit so a chat payload
    cannot inject fields the gateway does not name."""
    out: list[ToolRequest] = []
    for payload in payloads:
        out.append(
            ToolRequest(
                tool=str(payload.get("tool", "")),
                args=dict(payload.get("args", {})),
                actor=str(payload.get("actor", "chat")),
                role=str(payload.get("role", "none")),
                cwd=str(payload.get("cwd", "/workspace")),
            )
        )
    return out
