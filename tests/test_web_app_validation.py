"""Input-validation tests for web/app.py auth endpoints.

A JSON body that is not an object (array, string, number) must be rejected
with 400, never crash the handler with an AttributeError (HTTP 500).
"""

import pytest

from web.app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


NON_OBJECT_BODIES = [[1, 2], "text", 42, None]


@pytest.mark.parametrize("endpoint", ["/api/auth/login", "/api/auth/register"])
@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_mobile_auth_rejects_non_object_json(client, endpoint, body):
    r = client.post(endpoint, json=body)
    assert r.status_code == 400
    assert 'error' in r.get_json()


@pytest.mark.parametrize("endpoint", ["/login", "/register"])
@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_form_auth_rejects_non_object_json(client, endpoint, body):
    r = client.post(endpoint, json=body)
    assert r.status_code == 400
    assert 'error' in r.get_json()


def test_login_still_works_for_valid_json(client):
    r = client.post('/api/auth/login', json={'username': 'nobody', 'password': 'wrong'})
    assert r.status_code == 401


def test_form_login_still_accepts_form_encoded_body(client):
    r = client.post('/login', data={'username': '', 'password': ''})
    assert r.status_code == 400


def test_register_rejects_short_password(client):
    r = client.post('/api/auth/register', json={
        'username': 'u1', 'email': 'u1@example.com', 'password': 'short',
    })
    assert r.status_code == 400
