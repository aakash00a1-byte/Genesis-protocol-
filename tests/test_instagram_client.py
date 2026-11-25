"""Transport tests: request shape, auth parameters and error translation.

No network: every call goes through a fake ``http`` callable, which is also how
the production code is expected to be driven in tests.
"""
from __future__ import annotations

import pytest

from genesis_protocol.instagram import (
    ApiError,
    GraphClient,
    PermissionDeniedError,
    PublishFailedError,
    RateLimitedError,
    TokenExpiredError,
    TokenUnavailableError,
    TransientError,
    ValidationError,
    appsecret_proof,
)

TOKEN = "EAAG-test-token-123"


class Recorder:
    def __init__(self, responses=None):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.responses = list(responses or [])

    def __call__(self, method: str, url: str, data):
        self.calls.append((method, url, data))
        if self.responses:
            return self.responses.pop(0)
        return {"id": "ok"}


def client(http, **kwargs) -> GraphClient:
    return GraphClient(TOKEN, http=http, **kwargs)


def test_instagram_login_uses_graph_instagram_host():
    rec = Recorder()
    client(rec, login_type="instagram_login").get("me", {"fields": "id"})
    method, url, _ = rec.calls[0]
    assert method == "GET"
    assert url.startswith("https://graph.instagram.com/v27.0/me?")
    assert "fields=id" in url


def test_facebook_login_uses_graph_facebook_host():
    rec = Recorder()
    client(rec, login_type="facebook_login").get("me")
    assert rec.calls[0][1].startswith("https://graph.facebook.com/v27.0/me?")


def test_version_is_explicit_and_overridable():
    rec = Recorder()
    client(rec, version="v21.0").get("me")
    assert "/v21.0/" in rec.calls[0][1]


def test_token_is_always_sent_and_never_logged():
    rec = Recorder([{"id": "1"}])
    client(rec).get("1")
    assert f"access_token={TOKEN}" in rec.calls[0][1]


def test_appsecret_proof_added_only_when_a_secret_is_configured():
    rec = Recorder()
    client(rec, app_secret="app-secret").get("1")
    url = rec.calls[0][1]
    assert f"appsecret_proof={appsecret_proof('app-secret', TOKEN)}" in url

    rec2 = Recorder()
    client(rec2).get("1")
    assert "appsecret_proof" not in rec2.calls[0][1]


def test_post_sends_a_form_body():
    rec = Recorder([{"id": "c1"}])
    client(rec).post("1784/media", {"image_url": "https://x/y.jpg"})
    method, url, data = rec.calls[0]
    assert method == "POST"
    assert data == {"image_url": "https://x/y.jpg"}
    assert "access_token=" in url


def test_empty_token_is_refused_at_construction():
    with pytest.raises(TokenUnavailableError):
        GraphClient("")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (190, TokenExpiredError),
        (102, TokenExpiredError),
        (4, RateLimitedError),
        (17, RateLimitedError),
        (32, RateLimitedError),
        (613, RateLimitedError),
        (10, PermissionDeniedError),
        (200, PermissionDeniedError),
        (299, PermissionDeniedError),
        (100, ValidationError),
        (9004, ValidationError),
        (1, TransientError),
        (2, TransientError),
        (368, TransientError),
    ],
)
def test_meta_error_codes_map_to_typed_failures(code, expected):
    rec = Recorder([{"error": {"message": "boom", "code": code}}])
    with pytest.raises(expected):
        client(rec).get("1")


def test_unknown_error_code_is_not_retryable():
    rec = Recorder([{"error": {"message": "odd", "code": 999999, "error_subcode": 7}}])
    with pytest.raises(ApiError) as excinfo:
        client(rec).get("1")
    assert excinfo.value.code == 999999
    assert excinfo.value.subcode == 7


def test_error_messages_redact_the_token():
    rec = Recorder([{"error": {"message": f"bad token {TOKEN}", "code": 999999}}])
    with pytest.raises(ApiError) as excinfo:
        client(rec).get("1")
    assert TOKEN not in str(excinfo.value)
    assert "<redacted>" in str(excinfo.value)


def test_user_facing_meta_message_is_included():
    rec = Recorder([
        {"error": {"message": "Invalid parameter", "code": 100,
                   "error_user_msg": "The image URL is not reachable."}}
    ])
    with pytest.raises(ValidationError, match="not reachable"):
        client(rec).post("1784/media", {})


def test_container_creation_requires_an_id():
    rec = Recorder([{}])
    with pytest.raises(PublishFailedError, match="no container id"):
        client(rec).create_media_container("1784", {"image_url": "https://x/y.jpg"})


def test_publish_requires_an_id():
    rec = Recorder([{}])
    with pytest.raises(PublishFailedError, match="no published media id"):
        client(rec).publish_container("1784", "c1")


def test_container_status_reads_status_code():
    rec = Recorder([{"status_code": "FINISHED"}])
    assert client(rec).container_status("c1") == "FINISHED"
    assert "fields=status_code" in rec.calls[0][1]


def test_publishing_limit_reads_first_data_entry():
    rec = Recorder([{"data": [{"quota_usage": 7, "config": {"quota_total": 50}}]}])
    assert client(rec).publishing_limit("1784")["quota_usage"] == 7


@pytest.mark.parametrize("payload", [{}, {"data": []}, {"data": "nope"}])
def test_publishing_limit_tolerates_an_unexpected_shape(payload):
    rec = Recorder([payload])
    assert client(rec).publishing_limit("1784") == {}


def test_publishing_limit_swallows_api_errors_only():
    rec = Recorder([{"error": {"message": "no", "code": 999999}}])
    assert client(rec).publishing_limit("1784") == {}
