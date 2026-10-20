"""Telegram transport (Bot API, zero dependencies).

Long-polls ``getUpdates`` and replies with ``sendMessage``. The bot token is
read from configuration and never logged. The transport only moves text — every
decision is made by ``ChatGateway``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .transport import HttpResponse, TransportError, default_get, default_post


class TelegramClient:
    name = "telegram"

    def __init__(
        self,
        token: str,
        *,
        api_base: str = "https://api.telegram.org",
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

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self._token}/{method}"

    def get_updates(
        self, *, offset: int | None = None, timeout: int = 0, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not self.configured:
            raise TransportError("telegram: no bot token configured")
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset
        resp = self._get(self._url("getUpdates"), params=params, timeout=self._timeout)
        body = resp.body if isinstance(resp.body, dict) else {}
        result = body.get("result", [])
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: str, text: str) -> HttpResponse:
        if not self.configured:
            raise TransportError("telegram: no bot token configured")
        return self._post(
            self._url("sendMessage"),
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=self._timeout,
        )
