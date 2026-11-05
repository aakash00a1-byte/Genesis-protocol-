"""Tests for how GLUTEN reports a failure to the user.

The web UI shows the agent's response text verbatim. When no provider key is
configured the agent used to answer "Response Generation Issue ... try
rephrasing your question", which blames the question for a deployment gap and
suggests a retry that cannot help. The wording must match the actual cause.
"""

import pytest

from genesis_protocol.ai.failure_communicator import (
    FailureCommunicator,
    FailureType,
    get_failure_communicator,
)


@pytest.fixture
def fc():
    return FailureCommunicator()


def test_no_providers_message_names_the_missing_key(fc):
    text = fc.communicate(
        failure_type=FailureType.NO_PROVIDERS,
        reason="No provider API key is configured",
        query="hello",
    )
    assert "GROQ_API_KEY" in text
    assert "restart" in text.lower()
    # It must not blame the question.
    assert "rephrasing" not in text.lower()
    assert "Response Generation Issue" not in text


def test_provider_empty_does_not_tell_the_user_to_rephrase(fc):
    text = fc.communicate(
        failure_type=FailureType.PROVIDER_EMPTY,
        reason="Provider returned empty or invalid response",
        attempts=["primary_provider"],
        query="hello",
    )
    assert "rephrasing" not in text.lower()


def test_provider_error_does_not_tell_the_user_to_change_the_query(fc):
    text = fc.communicate(
        failure_type=FailureType.PROVIDER_ERROR,
        reason="HTTP 502 from provider",
        attempts=["primary_provider"],
        query="hello",
    )
    assert "different query" not in text.lower()


def test_failure_communicator_never_says_plain_sorry(fc):
    """The class documents this rule; hold it to it."""
    for ftype in FailureType:
        text = fc.communicate(
            failure_type=ftype,
            reason="test",
            attempts=["primary_provider"],
            query="hello",
        )
        assert "sorry" not in text.lower()


def test_singleton_is_returned():
    assert get_failure_communicator() is get_failure_communicator()


def test_diagnostics_reports_every_provider_and_no_fake_backends():
    """Diagnostics must not claim a provider or backend that is not there.

    It used to hardcode vector_db='chroma' and cache='redis' regardless of what
    was installed, and reported only groq.
    """
    import importlib
    import os

    os.environ.setdefault('SECRET_KEY', 'test-secret')
    app_module = importlib.import_module('web.app')
    client = app_module.app.test_client()
    resp = client.get('/api/diagnostics')
    assert resp.status_code == 200
    data = resp.get_json()

    env = data['environment']
    for provider in app_module.PROVIDER_ENV_VARS:
        assert f'{provider}_configured' in env, provider

    # No secret value may leak into the payload.
    assert 'GROQ_API_KEY' not in resp.get_data(as_text=True)

    memory = data['memory']
    assert memory['vector_db'].startswith('chroma'), memory['vector_db']
    assert '(not installed)' in memory['vector_db'] or '(available)' in memory['vector_db']
    assert 'redis' in memory['cache']
