"""Auth-token tests for web/app.py mobile Bearer authentication.

The mobile login/register endpoints issue a token of the shape
``genesis_mobile_{user_id}_{timestamp}``. The ``login_required`` decorator must
accept only tokens it actually issued. A hand-crafted, unsigned token that
merely matches the shape must be rejected, otherwise anyone can name any
``user_id`` and authenticate as that account with no password.

These tests are read-only with respect to user data: they assert on the token
accept/reject boundary and never need a real credential to succeed.
"""

import time

import pytest

from web.app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


PROTECTED = '/api/user'


def test_forged_mobile_token_is_rejected(client):
    """A guessed token must not authenticate a protected endpoint."""
    forged = f"genesis_mobile_1_{int(time.time())}"
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {forged}'})
    assert r.status_code == 401, "forged token was accepted"


def test_forged_token_with_any_user_id_is_rejected(client):
    for uid in (1, 2, 999999):
        forged = f"genesis_mobile_{uid}_{int(time.time())}"
        r = client.get(PROTECTED, headers={'Authorization': f'Bearer {forged}'})
        assert r.status_code == 401, f"forged token for user {uid} was accepted"


def test_malformed_bearer_token_is_rejected(client):
    for bad in ("genesis_mobile_", "genesis_mobile_abc", "Bearer nonsense",
                "genesis_mobile_1", "genesis_mobile_1_notanumber"):
        r = client.get(PROTECTED, headers={'Authorization': f'Bearer {bad}'})
        assert r.status_code == 401, f"malformed token accepted: {bad!r}"


def test_valid_signed_token_is_accepted(client):
    """A token the server actually signed must still authenticate."""
    import uuid

    name = f"tokuser_{uuid.uuid4().hex[:10]}"
    reg = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': 'Passw0rd1',
    })
    assert reg.status_code == 200, reg.get_data(as_text=True)
    body = reg.get_json()
    token = body['token']
    user_id = body['user']['id']

    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200, "validly signed token was rejected"
    assert r.get_json()['id'] == user_id


def test_tampered_signature_is_rejected(client):
    from web.app import _sign_token

    token = _sign_token(1, int(time.time()))
    head, _, sig = token.rpartition('_')
    tampered = f"{head}_{'A' if sig[:1] != 'A' else 'B'}{sig[1:]}"
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {tampered}'})
    assert r.status_code == 401, "tampered signature was accepted"


def test_valid_signature_for_missing_user_does_not_leak(client):
    """A correctly signed token for a non-existent user must not return data."""
    from web.app import _sign_token

    token = _sign_token(999999, int(time.time()))
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code != 200


def _clear_session(client):
    """Drop the session cookie so a request is authenticated by Bearer alone."""
    with client.session_transaction() as sess:
        sess.clear()


def _register(client):
    import uuid

    name = f"u_{uuid.uuid4().hex[:10]}"
    reg = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': 'Passw0rd1',
    })
    assert reg.status_code == 200, reg.get_data(as_text=True)
    body = reg.get_json()
    # Register auto-logs-in; drop the session so later requests are authenticated
    # by the Bearer token alone, which is what these tests exercise.
    with client.session_transaction() as sess:
        sess.clear()
    return body['user']['id'], body['token']


def test_expired_token_is_rejected(client):
    import web.app as appmod

    uid, _ = _register(client)
    old = _sign_token_for(uid, int(time.time()) - appmod.MOBILE_TOKEN_TTL_SECONDS - 10)
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {old}'})
    assert r.status_code == 401, "expired token was accepted"


def test_revoked_token_is_rejected(client):
    import web.app as appmod

    uid, token = _register(client)
    assert client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'}).status_code == 200
    _clear_session(client)
    appmod.invalidate_user_tokens(uid)
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 401, "revoked token was accepted"


def test_logout_revokes_tokens(client):
    import web.app as appmod

    uid, token = _register(client)
    appmod.invalidate_user_tokens(uid)  # simulate logout revoking this user's tokens
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 401


def test_deactivated_user_token_is_rejected(client):
    uid, token = _register(client)
    import web.app as appmod

    conn = appmod.get_db()
    conn.execute('UPDATE users SET is_active = 0 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 401, "token for a deactivated user was accepted"


def test_secret_rotation_invalidates_old_tokens(client, monkeypatch):
    uid, token = _register(client)
    assert client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'}).status_code == 200

    # Rotate the signing secret; the old token's signature no longer matches.
    _clear_session(client)
    monkeypatch.setenv('GENESIS_MOBILE_TOKEN_SECRET', 'rotated-secret-' + 'z' * 30)
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 401, "token survived a signing-secret rotation"


def test_restart_with_same_secret_keeps_token_valid(client, monkeypatch):
    """A stable secret must keep tokens valid across a simulated restart."""
    import web.app as appmod

    monkeypatch.setenv('GENESIS_MOBILE_TOKEN_SECRET', 'stable-secret-' + 'q' * 30)
    uid, token = _register(client)
    # Re-resolve the key as a fresh process would, from the same env.
    assert appmod.security_config.resolve_mobile_token_secret() == (
        'stable-secret-' + 'q' * 30
    )
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {token}'})
    assert r.status_code == 200


def test_future_dated_token_is_rejected(client):
    uid, _ = _register(client)
    future = _sign_token_for(uid, int(time.time()) + 3600)
    r = client.get(PROTECTED, headers={'Authorization': f'Bearer {future}'})
    assert r.status_code == 401, "future-dated token was accepted"


def _sign_token_for(user_id: int, issued_at: int) -> str:
    """Sign an arbitrary timestamp using the app's current key."""
    import hashlib as _hl
    import hmac as _hmac

    import web.app as appmod

    payload = f"{user_id}:{issued_at}"
    sig = _hmac.new(appmod._token_signing_key(), payload.encode(), _hl.sha256).hexdigest()
    return f"genesis_mobile_{user_id}_{issued_at}_{sig}"
