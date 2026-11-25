"""Account registry: one record per Instagram professional account (per client).

An account is the unit of publishing. Each one carries its own token variable,
its own login type and its own limits, and a publish call names exactly one
account - there is no "default account" fallback, because silently publishing a
client's content to another client's account is the worst failure this module
could have.

Records live in JSON (``IG_ACCOUNTS_FILE``, default ``data/instagram_accounts.json``)::

    {"accounts": [
      {"account_id": "acme-cafe", "client_id": "acme",
       "ig_user_id": "17841400000000000", "username": "acme.cafe",
       "login_type": "instagram_login",
       "token_env": "IG_TOKEN_ACME", "token_expires_at": "2027-01-31T00:00:00Z"}
    ]}

Only the *name* of the token variable is stored here. The value stays in the
environment (or the platform's secret store) and is never written to disk.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import AccountDisabledError, AccountInvalidError, UnknownAccountError, ValidationError
from .models import parse_iso

LOGIN_TYPES = ("instagram_login", "facebook_login")
DEFAULT_ACCOUNTS_FILE = "data/instagram_accounts.json"


@dataclass(frozen=True)
class InstagramAccount:
    """One Instagram professional account belonging to one client."""

    account_id: str
    client_id: str
    ig_user_id: str
    username: str = ""
    login_type: str = "instagram_login"
    token_env: str = ""
    app_secret_env: str = "IG_APP_SECRET"
    page_id: str = ""
    token_expires_at: str = ""
    enabled: bool = True
    daily_cap: int = 25
    stories_supported: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def validate_account(account: InstagramAccount) -> None:
    """Raise ``AccountInvalidError`` unless the record is usable as written."""
    if not account.account_id.strip():
        raise AccountInvalidError("account_id is empty")
    if not account.client_id.strip():
        raise AccountInvalidError(f"{account.account_id}: client_id is empty")
    if not account.ig_user_id.isdigit():
        raise AccountInvalidError(f"{account.account_id}: ig_user_id must be numeric")
    if account.login_type not in LOGIN_TYPES:
        raise AccountInvalidError(
            f"{account.account_id}: login_type must be one of {LOGIN_TYPES}"
        )
    if account.login_type == "facebook_login" and not account.page_id.isdigit():
        raise AccountInvalidError(
            f"{account.account_id}: facebook_login needs a numeric page_id"
        )
    if not account.token_env:
        raise AccountInvalidError(f"{account.account_id}: token_env is empty")
    if account.daily_cap < 0:
        raise AccountInvalidError(f"{account.account_id}: daily_cap must be >= 0")
    if account.token_expires_at:
        try:
            parse_iso(account.token_expires_at)
        except ValidationError as exc:
            raise AccountInvalidError(
                f"{account.account_id}: token_expires_at must be ISO-8601 ({exc})"
            ) from exc


class AccountRegistry:
    """Accounts loaded from disk, validated on load, looked up by exact id."""

    def __init__(self, accounts: Iterable[InstagramAccount] = ()):
        self._accounts: dict[str, InstagramAccount] = {}
        for account in accounts:
            validate_account(account)
            if account.account_id in self._accounts:
                raise AccountInvalidError(f"duplicate account_id {account.account_id!r}")
            self._accounts[account.account_id] = account

    # -- construction -------------------------------------------------
    @classmethod
    def from_file(cls, path: str | os.PathLike[str] | None = None) -> AccountRegistry:
        """Load the registry; a missing file is an empty registry, not an error."""
        target = Path(path or os.environ.get("IG_ACCOUNTS_FILE", DEFAULT_ACCOUNTS_FILE))
        if not target.exists():
            return cls()
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise AccountInvalidError(f"cannot read {target}: {exc}") from exc
        if not isinstance(payload, dict):
            raise AccountInvalidError(f"{target}: top level must be an object")
        records = payload.get("accounts", [])
        if not isinstance(records, list):
            raise AccountInvalidError(f"{target}: 'accounts' must be a list")
        accounts = []
        for record in records:
            if not isinstance(record, dict):
                raise AccountInvalidError(f"{target}: each account must be an object")
            accounts.append(InstagramAccount(**record))
        return cls(accounts)

    # -- access -------------------------------------------------------
    def __len__(self) -> int:
        return len(self._accounts)

    def __iter__(self):
        return iter(self._accounts.values())

    def get(self, account_id: str, *, require_enabled: bool = True) -> InstagramAccount:
        """Return the account, or raise. Never falls back to another account."""
        account = self._accounts.get(account_id)
        if account is None:
            raise UnknownAccountError(f"no such account: {account_id!r}")
        if require_enabled and not account.enabled:
            raise AccountDisabledError(f"account {account_id!r} is disabled")
        return account

    def for_client(self, client_id: str) -> list[InstagramAccount]:
        return [a for a in self._accounts.values() if a.client_id == client_id]

    def clients(self) -> list[str]:
        return sorted({a.client_id for a in self._accounts.values()})


def load_registry(path: str | None = None) -> AccountRegistry:
    return AccountRegistry.from_file(path)
