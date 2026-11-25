"""Thin transport for Meta's Instagram Graph API.

Only two things live here: building the request (host, API version, token,
``appsecret_proof``) and translating Meta's error payload into our typed
failures. Orchestration - approvals, dedupe, retries, polling - stays in
``publisher.py`` so this layer stays replaceable and easy to fake in tests.

Hosts, per Meta's Instagram Platform overview: the Instagram-Login setup calls
``graph.instagram.com`` and the Facebook-Login setup calls ``graph.facebook.com``.
The API version is explicit because Meta versions the API and a silent default
change would be a production surprise.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from .errors import (
    ApiError,
    PermissionDeniedError,
    PublishFailedError,
    RateLimitedError,
    TokenExpiredError,
    TokenUnavailableError,
    TransientError,
    ValidationError,
)
from .tokens import appsecret_proof, resolve_app_secret, resolve_token

DEFAULT_VERSION = "v27.0"
HOSTS = {
    "instagram_login": "https://graph.instagram.com",
    "facebook_login": "https://graph.facebook.com",
}

# Meta's documented error codes. Anything else becomes ApiError and is not
# retried, so an unknown failure never turns into a publish storm.
CODE_TOKEN = {102, 190, 463}
CODE_RATE = {4, 17, 32, 613}
CODE_PERMISSION = {10, *range(200, 300)}
CODE_VALIDATION = {100, 9004}
CODE_TRANSIENT = {1, 2, 368}

HttpFn = Callable[[str, str, Mapping[str, str] | None], Any]


def _default_http(method: str, url: str, data: Mapping[str, str] | None) -> Any:
    if method == "GET":
        request = urllib.request.Request(url, method="GET")  # noqa: S310 - fixed Meta host
    else:
        request = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data or {}).encode("utf-8"),
            method=method,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )  # noqa: S310 - fixed Meta host
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(body or "{}")
        except ValueError:
            payload = {}
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            return {"error": error, "__status": exc.code}
        raise TransientError(f"HTTP {exc.code} with an unreadable body") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransientError(f"network failure: {type(exc).__name__}") from exc


class GraphClient:
    """One account's authenticated view of the Instagram Graph API."""

    def __init__(
        self,
        token: str,
        *,
        login_type: str = "instagram_login",
        app_secret: str = "",
        http: HttpFn | None = None,
        version: str | None = None,
        host: str | None = None,
    ):
        if not token:
            raise TokenUnavailableError("GraphClient needs an access token")
        self._token = token
        self._app_secret = app_secret
        self._http = http or _default_http
        self.version = version or DEFAULT_VERSION
        self.host = host or HOSTS.get(login_type, HOSTS["instagram_login"])

    # -- request building ---------------------------------------------
    def _redact(self, text: str) -> str:
        return text.replace(self._token, "<redacted>") if self._token else text

    def _auth_params(self) -> dict[str, str]:
        params = {"access_token": self._token}
        if self._app_secret:
            params["appsecret_proof"] = appsecret_proof(self._app_secret, self._token)
        return params

    def _url(self, path: str, params: Mapping[str, str] | None = None) -> str:
        merged = dict(params or {})
        merged.update(self._auth_params())
        query = urllib.parse.urlencode(merged)
        return f"{self.host}/{self.version}/{path.lstrip('/')}?{query}"

    # -- calls ---------------------------------------------------------
    def get(self, path: str, params: Mapping[str, str] | None = None) -> dict:
        payload = self._http("GET", self._url(path, params), None)
        return self._unwrap(payload)

    def post(self, path: str, data: Mapping[str, str] | None = None) -> dict:
        payload = self._http("POST", self._url(path), dict(data or {}))
        return self._unwrap(payload)

    # -- error translation --------------------------------------------
    def _unwrap(self, payload: Any) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("Meta returned a non-object payload")
        error = payload.get("error")
        if not isinstance(error, dict):
            return payload
        code = error.get("code")
        subcode = error.get("error_subcode")
        message = self._redact(str(error.get("message") or "unknown error"))
        user_message = self._redact(str(error.get("error_user_msg") or "")).strip()
        detail = f"{message}{f' — {user_message}' if user_message else ''}"
        code_int = int(code) if isinstance(code, int) else None

        if code_int in CODE_TOKEN:
            raise TokenExpiredError(f"Meta rejected the token (code {code_int}): {detail}")
        if code_int in CODE_RATE:
            raise RateLimitedError(f"Meta rate limit (code {code_int}): {detail}")
        if code_int in CODE_PERMISSION:
            raise PermissionDeniedError(
                f"missing permission (code {code_int}): {detail}. "
                "Check the app's access level and the token's granted scopes."
            )
        if code_int in CODE_VALIDATION:
            raise ValidationError(f"Meta rejected the request (code {code_int}): {detail}")
        if code_int in CODE_TRANSIENT:
            raise TransientError(f"temporary Meta failure (code {code_int}): {detail}")
        raise ApiError(detail, code=code_int, subcode=subcode if isinstance(subcode, int) else None)

    # -- endpoints -----------------------------------------------------
    def create_media_container(self, ig_user_id: str, params: Mapping[str, str]) -> str:
        payload = self.post(f"{ig_user_id}/media", params)
        container_id = str(payload.get("id") or "")
        if not container_id:
            raise PublishFailedError("Meta returned no container id")
        return container_id

    def container_status(self, container_id: str) -> str:
        payload = self.get(container_id, {"fields": "status_code,status"})
        return str(payload.get("status_code") or "")

    def publish_container(self, ig_user_id: str, container_id: str) -> str:
        payload = self.post(f"{ig_user_id}/media_publish", {"creation_id": container_id})
        media_id = str(payload.get("id") or "")
        if not media_id:
            raise PublishFailedError("Meta returned no published media id")
        return media_id

    def publishing_limit(self, ig_user_id: str) -> dict:
        """Best-effort read of the account's publishing quota.

        Meta enforces the limit itself; this is for observability, so an
        unexpected payload shape is reported as an empty dict rather than being
        allowed to block a publish.
        """
        try:
            payload = self.get(f"{ig_user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        except ApiError:
            return {}
        data = payload.get("data")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return {}


def client_for_account(
    account,
    env: Mapping[str, str] | None = None,
    http: HttpFn | None = None,
    version: str | None = None,
) -> GraphClient:
    """Build a client for one account, reading the token it names."""
    return GraphClient(
        resolve_token(account, env),
        login_type=account.login_type,
        app_secret=resolve_app_secret(account, env),
        http=http,
        version=version,
    )
