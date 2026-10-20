"""Shared HTTP helpers for provider adapters.

Includes a pluggable HTTP transport so tests inject fakes with zero network
and per-provider base URLs resolve from configuration.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from genesis.core import ModelResult
from genesis.exceptions import (
    ProviderError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)

HttpPost = Callable[..., Any]
HttpGet = Callable[..., Any]


def default_post(url: str, **kwargs: Any) -> Any:
    return _urllib_request("POST", url, **kwargs)


def default_get(url: str, **kwargs: Any) -> Any:
    return _urllib_request("GET", url, **kwargs)


class _UrllibResponse:
    """Minimal response object matching the ``requests`` surface the adapters
    use (``status_code`` and ``json()``). Standard library only, so a live run
    needs no third-party HTTP client."""

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        import json

        return json.loads(self.text) if self.text else {}


def _urllib_request(method: str, url: str, **kwargs: Any) -> _UrllibResponse:
    import json
    import urllib.error
    import urllib.request

    timeout = kwargs.pop("timeout", 30) or 30
    payload = kwargs.pop("json", None)
    headers = dict(kwargs.pop("headers", {}) or {})
    params = kwargs.pop("params", None)
    if params:
        import urllib.parse

        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        status = exc.code
    except Exception as exc:  # noqa: BLE001 - normalize at the adapter boundary
        raise ProviderUnavailable(
            f"transport error: {exc}", provider="http", retryable=True, fallback=True
        ) from exc
    return _UrllibResponse(status, body)


def normalize_response(
    provider: str,
    model: str,
    payload: Any,
    *,
    text_path: str | None = None,
) -> ModelResult:
    """Normalize provider payloads into a ModelResult.

    `text_path` supports dotted paths like "choices.0.message.content". A
    malformed payload (missing keys, wrong types) yields an empty output rather
    than a raw KeyError/IndexError/TypeError.
    """
    if not isinstance(payload, dict):
        return ModelResult(
            provider=provider,
            model=model,
            output="" if payload is None else str(payload),
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            status="success",
        )
    text = _extract_text(payload, text_path)
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    return ModelResult(
        provider=provider,
        model=model,
        output=text,
        usage={
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        status="success",
    )


def normalize_error(exc: Exception, provider: str) -> ProviderError:
    """Map transport/protocol exceptions to normalized ProviderErrors."""
    if isinstance(exc, ProviderError):
        return exc
    status = getattr(exc, "status_code", None)
    msg = str(exc)
    if status is not None and status == 429:
        return ProviderRateLimited(
            f"{provider}: rate limited", provider=provider, status_code=429,
            retryable=True, fallback=True,
        )
    if status is not None and status >= 500:
        return ProviderUnavailable(
            f"{provider}: server error {status}", provider=provider,
            status_code=status, retryable=True, fallback=True,
        )
    if "timeout" in msg.lower() or isinstance(exc, TimeoutError):
        return ProviderTimeout(
            f"{provider}: timeout", provider=provider,
            retryable=True, fallback=True,
        )
    return ProviderUnavailable(
        f"{provider}: {msg[:200]}", provider=provider,
        status_code=status, retryable=True, fallback=True,
    )


def with_wall_clock_timeout(fn: Any, seconds: float, provider: str) -> Any:
    """Run `fn` with a wall-clock timeout even if the transport ignores the
    timeout kwarg. Returns the value or raises ProviderTimeout."""
    if seconds <= 0:
        return fn()
    result_holder: dict[str, Any] = {}
    error_holder: dict[str, Any] = {}

    def target() -> None:
        try:
            result_holder["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            error_holder["exc"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=seconds)
    if thread.is_alive():
        raise ProviderTimeout(
            f"{provider}: wall-clock timeout after {seconds}s",
            provider=provider,
            retryable=True,
            fallback=True,
        )
    if "exc" in error_holder:
        raise error_holder["exc"]
    return result_holder["value"]


def safe_json(resp: Any, provider: str) -> Any:
    """Parse a response body, normalizing an invalid JSON body.

    A provider that returns a non-JSON body must not surface a raw ValueError;
    it is normalized into a ProviderUnavailable so the router can fall back.
    """
    try:
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - normalize at the adapter boundary
        raise ProviderUnavailable(
            f"{provider}: malformed JSON response",
            provider=provider,
            retryable=True,
            fallback=True,
        ) from exc


def error_for_status(provider: str, status: int) -> ProviderError:
    """Map an HTTP status from a provider response to the right error type.

    A 429 must be a rate-limit error (retryable) and a 5xx an unavailable
    error; anything else is a generic provider error. Kept in one place so
    every adapter classifies a non-200 the same way.
    """
    if status == 429:
        return ProviderRateLimited(
            f"{provider}: rate limited",
            provider=provider,
            status_code=429,
            retryable=True,
            fallback=True,
        )
    if status >= 500:
        return ProviderUnavailable(
            f"{provider}: server error {status}",
            provider=provider,
            status_code=status,
            retryable=True,
            fallback=True,
        )
    return ProviderError(
        f"{provider}: HTTP {status}",
        provider=provider,
        status_code=status,
        retryable=False,
        fallback=True,
    )


def _extract_text(payload: Any, text_path: str | None) -> str:
    if not text_path:
        if isinstance(payload, dict) and "content" in payload:
            return str(payload["content"])
        return str(payload)
    node: Any = payload
    for part in text_path.split("."):
        # A malformed provider response must not raise a bare KeyError or
        # IndexError; treat any missing/invalid node as "no text".
        if isinstance(node, list):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return ""
        elif isinstance(node, dict):
            if part not in node:
                return ""
            node = node[part]
        else:
            return ""
    if isinstance(node, str):
        return node
    if isinstance(node, dict) and "content" in node:
        return str(node["content"])
    return str(node)


def measure(fn: Callable[[], Any]) -> tuple[Any, int]:
    start = time.time()
    result = fn()
    return result, int((time.time() - start) * 1000)
