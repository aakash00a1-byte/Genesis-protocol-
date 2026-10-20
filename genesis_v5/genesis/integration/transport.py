"""Zero-dependency HTTP transport for chat integrations.

Uses only ``urllib`` from the standard library so the integration runs in the
same offline environment as the rest of Genesis V5. Every call takes an
injectable ``http`` callable, so tests exercise the real request/response
handling with a fake transport and no network.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

# A bot token embedded in a path (Telegram's `/bot<token>/method`) must never
# reach a log line or an exception message.
_BOT_TOKEN_IN_URL = re.compile(r"/bot[^/\s]+")


def redact(text: str, *secrets: str) -> str:
    """Remove known secrets and any URL-embedded bot token from ``text``."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return _BOT_TOKEN_IN_URL.sub("/bot***", text)


@dataclass
class HttpResponse:
    status: int
    body: Any


class TransportError(Exception):
    """A transport failure (network, timeout, non-2xx)."""


def _request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:  # non-2xx still carries a body
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportError(redact(f"{method} {url} failed: {exc}")) from exc
    body: Any = None
    if raw:
        try:
            body = json.loads(raw)
        except ValueError:
            body = raw
    if not 200 <= status < 300:
        raise TransportError(
            redact(f"{method} {url} -> HTTP {status}: {str(body)[:200]}")
        )
    return HttpResponse(status=status, body=body)


def default_post(
    url: str,
    json: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    return _request("POST", url, json_body=json, headers=headers, timeout=timeout)


def default_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> HttpResponse:
    return _request("GET", url, params=params, headers=headers, timeout=timeout)
