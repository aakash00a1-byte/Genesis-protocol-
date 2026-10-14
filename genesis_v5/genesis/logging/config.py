"""Structured logging configuration.

Supports text or JSON output, configurable level/format, and an optional log
file. Secrets are never written: the message text is passed through the
Redactor before emitting.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

from genesis.config.settings import LoggingConfig
from genesis.security.redaction import Redactor


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "ts": record.created,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_REDACTOR = Redactor()


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.getMessage()  # ensure msg is resolved
        original = record.msg
        record.msg = _REDACTOR.redact(str(original)) if isinstance(original, str) else original
        return super().format(record)


def logging_setup(cfg: LoggingConfig | None = None) -> None:
    """Configure the root logger per LoggingConfig. Idempotent."""
    cfg = cfg or LoggingConfig()
    root = logging.getLogger()
    root.setLevel(cfg.level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    if cfg.file:
        handler: logging.Handler = logging.FileHandler(cfg.file)
    else:
        handler = logging.StreamHandler(sys.stderr)

    if cfg.json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(_RedactingFormatter(cfg.format or logging.BASIC_FORMAT))
    root.addHandler(handler)