"""Polling runners for the Discord and Telegram transports.

Each runner is a bounded loop: it polls a transport for new messages, hands
each to ``ChatGateway``, and posts the reply. A transport error is logged and
retried after ``poll_interval_seconds`` — a dropped poll never crashes the
process. Both runners stop cleanly when ``stop()`` is called.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from genesis.config.settings import IntegrationConfig

from .discord import DiscordClient
from .gateway import ChatGateway
from .telegram import TelegramClient

logger = logging.getLogger(__name__)


class _PollRunner:
    """Shared bounded-poll machinery for both platforms."""

    name = "chat"

    def __init__(
        self,
        *,
        config: IntegrationConfig,
        gateway: ChatGateway,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.gateway = gateway
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:  # noqa: BLE001 - a bad poll must not kill us
                logger.warning("%s poll failed: %s", self.name, exc)
            self._sleep(self.config.poll_interval_seconds)

    def poll_once(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class DiscordRunner(_PollRunner):
    name = "discord"

    def __init__(
        self,
        client: DiscordClient,
        *,
        config: IntegrationConfig,
        gateway: ChatGateway,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(config=config, gateway=gateway, sleep=sleep)
        self.client = client
        # channel -> last seen message id, so we only answer new messages.
        self._after: dict[str, str] = {}

    def poll_once(self) -> None:
        for channel in self.config.allowed_channels:
            messages = self.client.fetch_messages(
                channel, after=self._after.get(channel)
            )
            # Oldest first so replies keep order.
            for message in reversed(messages):
                msg_id = str(message.get("id", ""))
                if msg_id:
                    self._after[channel] = msg_id
                if message.get("author", {}).get("bot"):
                    continue
                content = str(message.get("content", ""))
                if not content:
                    continue
                sender = str(message.get("author", {}).get("id", "unknown"))
                reply = self.gateway.handle(
                    channel=channel, sender=sender, text=content
                )
                self.client.send_message(channel, reply.text)


class TelegramRunner(_PollRunner):
    name = "telegram"

    def __init__(
        self,
        client: TelegramClient,
        *,
        config: IntegrationConfig,
        gateway: ChatGateway,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__(config=config, gateway=gateway, sleep=sleep)
        self.client = client
        self._offset: int | None = None

    def poll_once(self) -> None:
        updates = self.client.get_updates(offset=self._offset)
        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                self._offset = update_id + 1
            message = update.get("message") or update.get("edited_message")
            if not isinstance(message, dict):
                continue
            chat = message.get("chat", {})
            channel = str(chat.get("id", ""))
            text = str(message.get("text", ""))
            if not text:
                continue
            sender = str(message.get("from", {}).get("id", "unknown"))
            reply = self.gateway.handle(
                channel=channel, sender=sender, text=text
            )
            self.client.send_message(channel, reply.text)


def build_runners(
    config: IntegrationConfig,
    gateway: ChatGateway,
    *,
    discord_client: DiscordClient | None = None,
    telegram_client: TelegramClient | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[_PollRunner]:
    """Build the runners the config enables. Returns [] when off or unconfigured."""
    if not config.enabled:
        return []
    runners: list[_PollRunner] = []
    if config.discord_enabled:
        client = discord_client or DiscordClient(
            config.discord_bot_token, api_base=config.discord_api_base
        )
        if client.configured:
            runners.append(
                DiscordRunner(client, config=config, gateway=gateway, sleep=sleep)
            )
        else:
            logger.info("discord enabled but no token configured; skipped")
    if config.telegram_enabled:
        client = telegram_client or TelegramClient(
            config.telegram_bot_token, api_base=config.telegram_api_base
        )
        if client.configured:
            runners.append(
                TelegramRunner(client, config=config, gateway=gateway, sleep=sleep)
            )
        else:
            logger.info("telegram enabled but no token configured; skipped")
    return runners
