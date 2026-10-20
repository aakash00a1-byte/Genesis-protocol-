"""Discord transport (REST only, zero dependencies).

Reads messages with the channel-messages endpoint and posts replies with the
channel-messages POST endpoint. No gateway WebSocket is used, so there is no
new runtime dependency; the bot token is read from configuration and never
logged. The transport only moves text — every decision is made by
``ChatGateway``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .transport import HttpResponse, TransportError, default_get, default_post


class DiscordClient:
    name = "discord"

    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://discord.com/api/v10",
        http_get: Callable[..., HttpResponse] | None = None,
        http_post: Callable[..., HttpResponse] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._token = token
        self.api_base = api_base.rstrip("/")
        self._get = http_get or default_get
        self._post = http_post or default_post
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bot {self._token}"}

    def fetch_messages(
        self, channel_id: str, *, after: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise TransportError("discord: no bot token configured")
        params: dict[str, Any] = {"limit": limit}
        if after:
            params["after"] = after
        resp = self._get(
            f"{self.api_base}/channels/{channel_id}/messages",
            params=params,
            headers=self._headers(),
            timeout=self._timeout,
        )
        body = resp.body
        return body if isinstance(body, list) else []

    def send_message(self, channel_id: str, content: str) -> HttpResponse:
        if not self.configured:
            raise TransportError("discord: no bot token configured")
        return self._post(
            f"{self.api_base}/channels/{channel_id}/messages",
            json={"content": content[:2000]},
            headers=self._headers(),
            timeout=self._timeout,
        )
