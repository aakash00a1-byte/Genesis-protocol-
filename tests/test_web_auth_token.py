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
