"""Tests for production security configuration (web/security_config.py).

Each test sets GENESIS_ENV explicitly so behaviour does not depend on the
ambient environment. Production must fail closed on missing or shipped-default
secrets; development must stay runnable.
"""
import pytest

from web import security_config as sc


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (
        "GENESIS_ENV",
        "SECRET_KEY",
        "GENESIS_MOBILE_TOKEN_SECRET",
        "ADMIN_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


STRONG = "a" * 40


# --- environment detection -------------------------------------------------
def test_is_production_only_for_exact_production(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    assert sc.is_production() is True
    monkeypatch.setenv("GENESIS_ENV", "Production")
    assert sc.is_production() is True
    monkeypatch.setenv("GENESIS_ENV", "staging")
    assert sc.is_production() is False


# --- SECRET_KEY ------------------------------------------------------------
def test_prod_requires_secret_key(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_secret_key()


def test_prod_rejects_shipped_default_secret_key(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "genesis-secret-key-change-in-production")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_secret_key()


def test_prod_rejects_short_secret_key(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_secret_key()


def test_prod_accepts_strong_secret_key(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", STRONG)
    assert sc.resolve_secret_key() == STRONG


def test_dev_has_stable_nonempty_secret_key(monkeypatch):
    first = sc.resolve_secret_key()
    assert first and first not in sc.PLACEHOLDER_SECRETS
    # Stable across calls so sessions survive a restart in development.
    assert sc.resolve_secret_key() == first


# --- mobile token secret ---------------------------------------------------
def test_prod_requires_dedicated_mobile_token_secret(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", STRONG)
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_mobile_token_secret()


def test_prod_rejects_shipped_default_mobile_secret(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("GENESIS_MOBILE_TOKEN_SECRET", "genesis-admin-2024")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_mobile_token_secret()


def test_prod_accepts_strong_mobile_secret(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("GENESIS_MOBILE_TOKEN_SECRET", STRONG)
    assert sc.resolve_mobile_token_secret() == STRONG


def test_mobile_secret_is_stable_so_tokens_survive_restart(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("GENESIS_MOBILE_TOKEN_SECRET", STRONG)
    assert sc.resolve_mobile_token_secret() == sc.resolve_mobile_token_secret()


# --- admin bootstrap -------------------------------------------------------
def test_prod_requires_admin_password(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_admin_bootstrap_password()


def test_prod_rejects_shipped_default_admin_password(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", "genesis-admin-2024")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_admin_bootstrap_password()


def test_prod_accepts_strong_admin_password(monkeypatch):
    monkeypatch.setenv("GENESIS_ENV", "production")
    monkeypatch.setenv("ADMIN_PASSWORD", STRONG)
    assert sc.resolve_admin_bootstrap_password() == STRONG


def test_dev_without_admin_password_provisions_nothing(monkeypatch):
    assert sc.resolve_admin_bootstrap_password() is None


def test_dev_rejects_shipped_default_admin_password(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "genesis-admin-2024")
    with pytest.raises(sc.InsecureConfigError):
        sc.resolve_admin_bootstrap_password()
