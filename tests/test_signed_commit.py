"""Signature verification contract for verified landing.

The gate must refuse an unsigned commit and must never mistake an unreadable
verdict for a valid signature.
"""

from __future__ import annotations

from genesis_protocol.evolution.signed_commit import (
    CommitSignature,
    commit_url,
    read_signature,
    signature_blockers,
)

REPO = "aakash00a1-byte/Genesis-protocol-"
SHA = "96512bbc0423a1b2c3d4e5f60718293a4b5c6d7e"


def _http_returning(payload):
    calls = []

    def http(method, url, body):
        calls.append((method, url, body))
        return payload

    http.calls = calls
    return http


def _commit(verified: bool, reason: str, signature_type=None, login="openhands-agent", sha=SHA):
    return {
        "sha": sha,
        "commit": {
            "verification": {
                "verified": verified,
                "reason": reason,
                "signature_type": signature_type,
            }
        },
        "author": {"login": login},
        "committer": {"login": login},
    }


def test_verified_commit_has_no_refusal():
    sig = read_signature(REPO, SHA, _http_returning(_commit(True, "valid", "ssh")))
    assert sig.verified is True
    assert sig.refusal() is None
    assert sig.signature_type == "ssh"


def test_unsigned_commit_is_refused_and_names_the_commit():
    sig = read_signature(REPO, SHA, _http_returning(_commit(False, "unsigned")))
    refusal = sig.refusal()
    assert refusal is not None
    assert SHA[:12] in refusal
    assert "unsigned" in refusal


def test_unverified_email_is_refused():
    sig = read_signature(REPO, SHA, _http_returning(_commit(False, "unverified_email")))
    assert sig.verified is False
    assert "unverified_email" in (sig.refusal() or "")


def test_network_failure_fails_closed():
    def boom(method, url, body):
        raise TimeoutError("api.github.com timed out")

    sig = read_signature(REPO, SHA, boom)
    assert sig.verified is False
    assert "unreadable" in sig.reason
    assert sig.refusal() is not None


def test_malformed_payload_fails_closed():
    for payload in (None, [], {"sha": SHA}, {"sha": SHA, "commit": {}}):
        sig = read_signature(REPO, SHA, _http_returning(payload))
        assert sig.verified is False, payload
        assert sig.refusal() is not None


def test_read_is_a_get_to_the_commit_endpoint():
    http = _http_returning(_commit(True, "valid", "gpg"))
    read_signature(REPO, SHA, http)
    method, url, body = http.calls[0]
    assert method == "GET"
    assert url == commit_url(REPO, SHA)
    assert body is None


def test_blockers_cover_every_commit_not_just_the_head():
    verdicts = {
        "aaa111": _commit(True, "valid", "ssh", sha="aaa111"),
        "bbb222": _commit(False, "unsigned", sha="bbb222"),
    }

    def http(method, url, body):
        return verdicts[url.rsplit("/", 1)[-1]]

    blockers = signature_blockers(REPO, ["aaa111", "bbb222"], http)
    assert len(blockers) == 1
    assert "bbb222" in blockers[0]


def test_all_signed_yields_no_blockers():
    http = _http_returning(_commit(True, "valid", "ssh"))
    assert signature_blockers(REPO, [SHA, SHA], http) == []


def test_empty_commit_list_is_not_an_error():
    assert signature_blockers(REPO, [], _http_returning({})) == []


def test_to_dict_reports_the_verdict_without_secrets():
    sig = CommitSignature(sha=SHA, verified=True, reason="valid", signature_type="ssh")
    as_dict = sig.to_dict()
    assert as_dict["verified"] is True
    assert as_dict["signature_type"] == "ssh"
    assert set(as_dict) == {"sha", "verified", "reason", "signature_type", "author", "committer"}
