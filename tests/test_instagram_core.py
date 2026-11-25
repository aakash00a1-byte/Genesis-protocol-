"""Core value types: post validation, the account registry, tokens and approvals.

These pin the constraints that come from Meta's documentation (public https
media, no alt text on stories/reels, carousel item counts) and the fail-closed
behaviour around accounts, tokens and approvals.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from genesis_protocol.instagram import (
    AccountDisabledError,
    AccountInvalidError,
    AccountRegistry,
    ApprovalGate,
    ApprovalRequiredError,
    InstagramAccount,
    MediaItem,
    Post,
    PostKind,
    TokenExpiredError,
    TokenUnavailableError,
    UnknownAccountError,
    ValidationError,
    appsecret_proof,
    assert_usable,
    inspect_token,
    mint_approval,
    validate_account,
    validate_post,
    verify_approval,
)

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
IMG = "https://cdn.example.com/a.jpg"
VID = "https://cdn.example.com/a.mp4"


def account(**overrides) -> InstagramAccount:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "ig_user_id": "17841400000000001",
        "username": "acme.cafe",
        "login_type": "instagram_login",
        "token_env": "IG_TOKEN_ACME",
        "token_expires_at": "2027-01-30T00:00:00Z",
    }
    base.update(overrides)
    return InstagramAccount(**base)


def post(kind=PostKind.IMAGE, media=(IMG,), caption="hello", **overrides) -> Post:
    base = {
        "account_id": "acme-cafe",
        "client_id": "acme",
        "kind": kind,
        "caption": caption,
        "media": tuple(MediaItem(url=url) for url in media),
    }
    base.update(overrides)
    return Post(**base)


# ---------------------------------------------------------------- posts


def test_image_post_is_valid():
    validate_post(post())


@pytest.mark.parametrize("url", [
    "http://cdn.example.com/a.jpg",          # not https
    "https://localhost/a.jpg",               # localhost
    "https://127.0.0.1/a.jpg",               # loopback
    "https://10.0.0.5/a.jpg",                # private
    "https://192.168.1.9/a.jpg",             # private
    "https://172.16.4.4/a.jpg",              # private
    "https://user:pw@cdn.example.com/a.jpg",  # credentials in the URL
    "not-a-url",
])
def test_media_must_be_public_https(url):
    with pytest.raises(ValidationError):
        validate_post(post(media=(url,)))


def test_story_with_alt_text_is_refused():
    bad = Post(
        account_id="acme-cafe",
        client_id="acme",
        kind=PostKind.STORY,
        media=(MediaItem(url=IMG, alt_text="a cup"),),
    )
    with pytest.raises(ValidationError, match="alt_text"):
        validate_post(bad)


def test_reel_needs_video():
    with pytest.raises(ValidationError, match="reel"):
        validate_post(post(kind=PostKind.REEL, media=(IMG,)))


def test_carousel_needs_two_to_twenty_items():
    with pytest.raises(ValidationError, match="at least 2"):
        validate_post(post(kind=PostKind.CAROUSEL, media=(IMG,)))
    with pytest.raises(ValidationError, match="at most 20"):
        validate_post(post(kind=PostKind.CAROUSEL, media=tuple(IMG for _ in range(21))))


def test_single_image_post_cannot_have_two_items():
    with pytest.raises(ValidationError, match="exactly one"):
        validate_post(post(media=(IMG, IMG)))


def test_caption_length_is_guarded():
    with pytest.raises(ValidationError, match="caption"):
        validate_post(post(caption="x" * 2201))


def test_post_requires_account_and_client():
    with pytest.raises(ValidationError):
        validate_post(post(account_id=""))
    with pytest.raises(ValidationError):
        validate_post(post(client_id=""))


# ------------------------------------------------------------- accounts


def test_registry_rejects_duplicate_account_ids():
    with pytest.raises(AccountInvalidError, match="duplicate"):
        AccountRegistry([account(), account()])


@pytest.mark.parametrize(
    "overrides",
    [
        {"ig_user_id": "not-a-number"},
        {"login_type": "personal"},
        {"token_env": ""},
        {"login_type": "facebook_login", "page_id": ""},
        {"client_id": ""},
        {"daily_cap": -1},
        {"token_expires_at": "not-a-date"},
    ],
)
def test_account_validation(overrides):
    with pytest.raises(AccountInvalidError):
        validate_account(account(**overrides))


def test_registry_lookup_never_falls_back():
    registry = AccountRegistry([account()])
    assert registry.get("acme-cafe").client_id == "acme"
    with pytest.raises(UnknownAccountError):
        registry.get("acme-cafe ")  # no fuzzy matching
    with pytest.raises(UnknownAccountError):
        registry.get("someone-else")


def test_disabled_account_is_refused():
    registry = AccountRegistry([account(enabled=False)])
    with pytest.raises(AccountDisabledError):
        registry.get("acme-cafe")
    # The record is still readable for reporting when the caller opts out.
    assert registry.get("acme-cafe", require_enabled=False).enabled is False


def test_registry_loads_from_json(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({"accounts": [account().to_dict()]}), encoding="utf-8")
    registry = AccountRegistry.from_file(path)
    assert len(registry) == 1
    assert registry.clients() == ["acme"]


def test_missing_accounts_file_is_an_empty_registry(tmp_path):
    registry = AccountRegistry.from_file(tmp_path / "nope.json")
    assert len(registry) == 0


def test_registry_rejects_a_corrupt_file(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AccountInvalidError):
        AccountRegistry.from_file(path)


def test_registry_groups_accounts_by_client():
    registry = AccountRegistry(
        [
            account(),
            account(account_id="acme-2", ig_user_id="17841400000000009"),
            account(account_id="bluebird", client_id="bluebird", ig_user_id="17841400000000002"),
        ]
    )
    assert [a.account_id for a in registry.for_client("acme")] == ["acme-cafe", "acme-2"]
    assert registry.clients() == ["acme", "bluebird"]


# --------------------------------------------------------------- tokens


def test_token_presence_and_expiry_are_reported_without_the_value():
    info = inspect_token(account(), env={"IG_TOKEN_ACME": "super-secret"}, now=NOW)
    assert info.present is True
    assert info.expired is False
    assert info.days_left > 60
    assert "super-secret" not in json.dumps(info.to_dict())


def test_missing_token_is_reported_not_invented():
    info = inspect_token(account(), env={}, now=NOW)
    assert info.present is False
    with pytest.raises(TokenUnavailableError):
        assert_usable(account(), env={}, now=NOW)


def test_expired_token_blocks_publishing():
    expired = account(token_expires_at="2026-11-01T00:00:00Z")
    info = inspect_token(expired, env={"IG_TOKEN_ACME": "t"}, now=NOW)
    assert info.expired is True
    with pytest.raises(TokenExpiredError):
        assert_usable(expired, env={"IG_TOKEN_ACME": "t"}, now=NOW)


def test_rotation_window_is_flagged():
    soon = account(token_expires_at=(NOW + timedelta(days=3)).isoformat())
    info = inspect_token(soon, env={"IG_TOKEN_ACME": "t"}, now=NOW)
    assert info.needs_rotation is True
    far = account(token_expires_at=(NOW + timedelta(days=40)).isoformat())
    assert inspect_token(far, env={"IG_TOKEN_ACME": "t"}, now=NOW).needs_rotation is False


def test_appsecret_proof_is_the_documented_hmac():
    # HMAC-SHA256 keyed by the app secret over the access token, hex encoded.
    import hashlib
    import hmac as hmac_mod

    expected = hmac_mod.new(b"secret", b"token", hashlib.sha256).hexdigest()
    assert appsecret_proof("secret", "token") == expected
    assert len(expected) == 64


# ------------------------------------------------------------- approvals


def test_approval_round_trip():
    token = mint_approval("s3cret", "acme-cafe", "fp1", ttl_seconds=60, now=1000)
    verify_approval("s3cret", token, "acme-cafe", "fp1", now=1010)


def test_approval_is_bound_to_account_and_content():
    token = mint_approval("s3cret", "acme-cafe", "fp1", ttl_seconds=60, now=1000)
    with pytest.raises(ApprovalRequiredError, match="does not match"):
        verify_approval("s3cret", token, "bluebird", "fp1", now=1010)
    with pytest.raises(ApprovalRequiredError, match="does not match"):
        verify_approval("s3cret", token, "acme-cafe", "fp2", now=1010)


def test_approval_expires():
    token = mint_approval("s3cret", "acme-cafe", "fp1", ttl_seconds=10, now=1000)
    with pytest.raises(ApprovalRequiredError, match="expired"):
        verify_approval("s3cret", token, "acme-cafe", "fp1", now=1011)


@pytest.mark.parametrize("token", ["", "nonsense", "v2.1.abc", "v1.notanint.abc"])
def test_malformed_approvals_are_refused(token):
    with pytest.raises(ApprovalRequiredError):
        verify_approval("s3cret", token, "acme-cafe", "fp1", now=1000)


def test_approval_fails_closed_without_a_secret():
    gate = ApprovalGate(secret="")
    assert gate.configured is False
    with pytest.raises(ApprovalRequiredError, match="not set"):
        gate.require("v1.1.abc", "acme-cafe", "fp1")


def test_approval_gate_from_env_reads_only_the_named_variable():
    gate = ApprovalGate.from_env({"IG_APPROVAL_SECRET": "abc"})
    assert gate.configured is True
    assert ApprovalGate.from_env({}).configured is False
