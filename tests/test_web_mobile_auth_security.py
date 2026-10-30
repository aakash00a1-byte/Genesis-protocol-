"""Independent adversarial tests for mobile Bearer authentication.

These tests attack the token boundary from the outside instead of repeating the
implementation's assumptions: forgery, tampering, expiry, revocation, privilege
escalation, browser/mobile session confusion and production configuration. Each
test runs against its own temporary database so results are deterministic and
do not depend on a shared genesis.db.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import subprocess
import sys
import time
import uuid

import pytest

import web.app as appmod
from web import security_config

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROTECTED = '/api/user'
ADMIN_API = '/api/admin/stats'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, 'DATABASE', str(tmp_path / 'genesis-test.db'))
    monkeypatch.setattr(appmod, '_token_epochs', {})
    monkeypatch.setattr(appmod, '_global_epoch', 0)
    appmod.init_db()
    appmod.app.config['TESTING'] = True
    with appmod.app.test_client() as c:
        yield c


def _bearer(token: str) -> dict:
    return {'Authorization': f'Bearer {token}'}


def _sign(user_id: int, issued_at: int, key: bytes | None = None) -> str:
    signing_key = key if key is not None else appmod._token_signing_key()
    sig = hmac.new(signing_key, f"{user_id}:{issued_at}".encode(), hashlib.sha256).hexdigest()
    return f"genesis_mobile_{user_id}_{issued_at}_{sig}"


def _clear(client) -> None:
    with client.session_transaction() as sess:
        sess.clear()


def _register(client, password: str = 'Passw0rd1'):
    name = f"u_{uuid.uuid4().hex[:10]}"
    r = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': password,
    })
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    _clear(client)  # drop the auto-login session; authenticate by Bearer only
    return body['user']['id'], body['token']


def _make_admin(client, password: str = 'AdminPass1') -> int:
    from werkzeug.security import generate_password_hash

    conn = appmod.get_db()
    cur = conn.execute(
        'INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
        ('admin', 'admin@example.com', generate_password_hash(password), 'admin'),
    )
    admin_id = cur.lastrowid
    conn.commit()
    conn.close()
    return admin_id


def _run_in_fresh_process(db_path: str, token: str) -> int:
    """Check a token in a brand-new interpreter against the same database."""
    script = (
        "import sys\n"
        f"sys.path.insert(0, {REPO_ROOT!r})\n"
        "import web.app as m\n"
        f"m.DATABASE = {db_path!r}\n"
        "m.init_db()\n"
        "m.app.config['TESTING'] = True\n"
        "c = m.app.test_client()\n"
        f"r = c.get('/api/user', headers={{'Authorization': 'Bearer ' + {token!r}}})\n"
        "print('STATUS', r.status_code)\n"
    )
    out = subprocess.run(
        [sys.executable, '-c', script], cwd=REPO_ROOT,
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    for line in out.stdout.splitlines():
        if line.startswith('STATUS'):
            return int(line.split()[1])
    raise AssertionError(f"no STATUS line:\n{out.stdout}\n{out.stderr}")


# --------------------------------------------------------------------------
# Token forgery and tampering
# --------------------------------------------------------------------------
def test_unsigned_token_for_any_id_is_rejected(client):
    for uid in (1, 2, 999999):
        forged = f"genesis_mobile_{uid}_{int(time.time())}"
        assert client.get(PROTECTED, headers=_bearer(forged)).status_code == 401


def test_wrong_signature_is_rejected(client):
    uid, _ = _register(client)
    forged = f"genesis_mobile_{uid}_{int(time.time())}_" + "0" * 64
    assert client.get(PROTECTED, headers=_bearer(forged)).status_code == 401


def test_modified_payload_with_stale_signature_is_rejected(client):
    uid, token = _register(client)
    _, issued_at, sig = token[len('genesis_mobile_'):].split('_')
    tampered = f"genesis_mobile_{uid}_{int(issued_at) - 100}_{sig}"
    assert client.get(PROTECTED, headers=_bearer(tampered)).status_code == 401


def test_signature_is_bound_to_user_id(client):
    uid_a, _ = _register(client)
    uid_b, _ = _register(client)
    ts = int(time.time())
    _, _, sig = _sign(uid_a, ts)[len('genesis_mobile_'):].split('_')
    forged = f"genesis_mobile_{uid_b}_{ts}_{sig}"
    assert client.get(PROTECTED, headers=_bearer(forged)).status_code == 401


def test_malformed_tokens_are_rejected(client):
    malformed = [
        "genesis_mobile_",
        "genesis_mobile_abc",
        "genesis_mobile_1_2",
        "genesis_mobile_1_2_3_4",
        f"genesis_mobile_x_1_{'a' * 64}",
        f"genesis_mobile_1_x_{'a' * 64}",
        "Bearer",
        "",
        "nonsense",
    ]
    for token in malformed:
        assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


# --------------------------------------------------------------------------
# Expiry and timestamps
# --------------------------------------------------------------------------
def test_expired_token_is_rejected(client):
    uid, _ = _register(client)
    old = _sign(uid, int(time.time()) - appmod.MOBILE_TOKEN_TTL_SECONDS - 10)
    assert client.get(PROTECTED, headers=_bearer(old)).status_code == 401


def test_token_just_inside_ttl_is_accepted(client):
    uid, _ = _register(client)
    token = _sign(uid, int(time.time()) - appmod.MOBILE_TOKEN_TTL_SECONDS + 30)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 200


def test_token_just_outside_ttl_is_rejected(client):
    uid, _ = _register(client)
    token = _sign(uid, int(time.time()) - appmod.MOBILE_TOKEN_TTL_SECONDS - 1)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_future_dated_token_is_rejected(client):
    """There is no forward clock-skew tolerance: a future token fails closed."""
    uid, _ = _register(client)
    token = _sign(uid, int(time.time()) + 3600)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_non_integer_timestamp_is_rejected(client):
    uid, _ = _register(client)
    token = f"genesis_mobile_{uid}_notanumber_{'0' * 64}"
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


# --------------------------------------------------------------------------
# Revocation
# --------------------------------------------------------------------------
def test_logout_revokes_the_presented_bearer_token(client):
    """A mobile client has no session; logout must revoke the token it sends."""
    uid, token = _register(client)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 200
    assert client.post('/api/auth/logout', headers=_bearer(token)).status_code == 200
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_revocation_survives_a_restart(client):
    """Revocation is persisted, so it must outlive the process."""
    uid, token = _register(client)
    db_path = appmod.DATABASE
    client.post('/api/auth/logout', headers=_bearer(token))
    assert _run_in_fresh_process(db_path, token) == 401


def test_deactivated_user_token_is_rejected(client):
    uid, token = _register(client)
    conn = appmod.get_db()
    conn.execute('UPDATE users SET is_active = 0 WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_admin_deactivation_revokes_the_token(client):
    uid, token = _register(client)
    admin_id = _make_admin(client)
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['username'] = 'admin'
    assert client.post(f'/api/admin/users/{uid}/toggle').status_code == 200
    _clear(client)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_deleted_user_token_is_rejected(client):
    uid, token = _register(client)
    conn = appmod.get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (uid,))
    conn.commit()
    conn.close()
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


# --------------------------------------------------------------------------
# Secret rotation
# --------------------------------------------------------------------------
def test_token_signed_with_old_secret_is_rejected_after_rotation(client, monkeypatch):
    uid, _ = _register(client)
    old_key = appmod._token_signing_key()
    token = _sign(uid, int(time.time()), key=old_key)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 200
    _clear(client)
    monkeypatch.setenv('GENESIS_MOBILE_TOKEN_SECRET', 'rotated-' + 'z' * 40)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


def test_global_epoch_rotation_invalidates_existing_tokens(client):
    uid, token = _register(client)
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 200
    _clear(client)
    appmod.rotate_token_epoch()
    assert client.get(PROTECTED, headers=_bearer(token)).status_code == 401


# --------------------------------------------------------------------------
# Privilege escalation
# --------------------------------------------------------------------------
def test_normal_user_bearer_cannot_reach_admin_api(client):
    _make_admin(client)
    _, token = _register(client)
    assert client.get(ADMIN_API, headers=_bearer(token)).status_code != 200


def test_normal_user_bearer_cannot_reach_admin_page(client):
    _make_admin(client)
    _, token = _register(client)
    assert client.get('/admin', headers=_bearer(token)).status_code != 200


def test_query_parameters_cannot_change_identity_or_role(client):
    uid, token = _register(client)
    r = client.get('/api/user?user_id=1&role=admin&id=1', headers=_bearer(token))
    body = r.get_json()
    assert r.status_code == 200
    assert body['id'] == uid, "identity came from a request parameter"
    assert body['role'] == 'user', "role came from a request parameter"


def test_admin_bearer_token_can_reach_admin_api(client):
    admin_id = _make_admin(client)
    token = _sign(admin_id, int(time.time()))
    assert client.get(ADMIN_API, headers=_bearer(token)).status_code == 200


def test_issued_admin_token_carries_admin_role(client):
    _make_admin(client, password='AdminPass1')
    r = client.post('/api/auth/login', json={'username': 'admin', 'password': 'AdminPass1'})
    body = r.get_json()
    assert body['user']['role'] == 'admin'
    _clear(client)
    assert client.get(ADMIN_API, headers=_bearer(body['token'])).status_code == 200


# --------------------------------------------------------------------------
# Browser-session and Bearer-token isolation
# --------------------------------------------------------------------------
def test_admin_cookie_plus_normal_bearer_is_denied_admin(client):
    """The two auth paths must not disagree about who the caller is."""
    admin_id = _make_admin(client)
    _, token = _register(client)
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['username'] = 'admin'
    assert client.get(ADMIN_API, headers=_bearer(token)).status_code != 200


def test_invalid_bearer_does_not_fall_back_to_admin_session(client):
    admin_id = _make_admin(client)
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['username'] = 'admin'
    forged = f"genesis_mobile_{admin_id}_{int(time.time())}_deadbeef"
    assert client.get(ADMIN_API, headers=_bearer(forged)).status_code == 401


def test_bearer_replaces_cookie_identity(client):
    admin_id = _make_admin(client)
    uid, token = _register(client)
    with client.session_transaction() as sess:
        sess['user_id'] = admin_id
        sess['role'] = 'admin'
        sess['username'] = 'admin'
    body = client.get('/api/user', headers=_bearer(token)).get_json()
    assert body['id'] == uid
    assert body['role'] == 'user'


def test_normal_session_cannot_reach_admin(client):
    uid, _ = _register(client)
    with client.session_transaction() as sess:
        sess['user_id'] = uid
        sess['role'] = 'user'
        sess['username'] = 'user'
    assert client.get(ADMIN_API).status_code != 200


# --------------------------------------------------------------------------
# Production configuration
# --------------------------------------------------------------------------
def test_production_requires_dedicated_mobile_secret(monkeypatch):
    monkeypatch.setenv('GENESIS_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'a' * 40)
    monkeypatch.delenv('GENESIS_MOBILE_TOKEN_SECRET', raising=False)
    with pytest.raises(security_config.InsecureConfigError):
        security_config.resolve_mobile_token_secret()


def test_dev_mobile_secret_is_not_the_session_secret(monkeypatch):
    """The session key must never be silently reused to sign tokens."""
    monkeypatch.delenv('GENESIS_ENV', raising=False)
    monkeypatch.setenv('SECRET_KEY', 'session-secret-value')
    monkeypatch.delenv('GENESIS_MOBILE_TOKEN_SECRET', raising=False)
    assert security_config.resolve_mobile_token_secret() != 'session-secret-value'


def test_production_startup_fails_without_mobile_secret():
    env = dict(os.environ, GENESIS_ENV='production', SECRET_KEY='a' * 40)
    env.pop('GENESIS_MOBILE_TOKEN_SECRET', None)
    out = subprocess.run(
        [sys.executable, '-c', 'import web.app'], cwd=REPO_ROOT,
        capture_output=True, text=True, env=env,
    )
    assert out.returncode != 0, "production started without a dedicated mobile secret"
    assert 'GENESIS_MOBILE_TOKEN_SECRET' in (out.stderr + out.stdout)


# --------------------------------------------------------------------------
# Error responses must not leak secrets
# --------------------------------------------------------------------------
def test_unauthorized_response_does_not_leak_token_or_secret(client):
    uid, _ = _register(client)
    forged = f"genesis_mobile_{uid}_{int(time.time())}_" + "0" * 64
    r = client.get(PROTECTED, headers=_bearer(forged))
    body = r.get_data(as_text=True)
    assert r.status_code == 401
    assert forged not in body
    assert appmod._token_signing_key().decode() not in body


def test_error_response_has_no_internal_details(client):
    r = client.get(PROTECTED, headers=_bearer('genesis_mobile_bad'))
    body = r.get_data(as_text=True)
    assert r.status_code == 401
    assert 'Traceback' not in body
    assert 'sqlite' not in body.lower()
