"""Short-lived, revocable credentials for GLUTEN agents.

An agent credential is a bearer token bound to exactly one agent identity. It is
short-lived (a TTL in seconds), may be single-use or bounded by a maximum use
count, and can be revoked - individually, per agent, or wholesale. The store
keeps only a SHA-256 hash of each token, so the raw secret exists exactly once
(in the return value of :meth:`CredentialStore.issue`) and is never persisted,
listed or logged.

Design rules:

1. Never expose a secret. ``issue`` returns the raw token to its caller and
   stores only a hash; every listing and serialisation reports the hash prefix,
   never the token.
2. Fail closed. An unknown, expired, exhausted, revoked or mismatched token
   fails verification.
3. Short-lived by default. A TTL is always applied; an unbounded credential is
   not offered.

This module does not decide permissions - it only proves *which* agent a token
belongs to and whether it is still valid.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# A credential must not outlive a work session by default.
DEFAULT_TTL_SECONDS = 900
MAX_TTL_SECONDS = 86_400


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CredentialCheck:
    """Outcome of verifying a credential."""

    ok: bool
    reason: str
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"ok": self.ok, "reason": self.reason, "agent_id": self.agent_id}


@dataclass
class Credential:
    """A stored credential. Holds a hash, never the token."""

    cred_id: str
    agent_id: str
    token_hash: str
    issued_at: str
    expires_at: str
    max_uses: int = 1
    uses: int = 0
    revoked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialise without the token. Only a short hash prefix is shown."""
        data = asdict(self)
        data.pop("token_hash", None)
        data["hash_prefix"] = self.token_hash[:12]
        return data


class CredentialStore:
    """Thread-safe store of short-lived agent credentials."""

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = str(Path("data") / "gluten_agent_credentials.json")
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._creds: Dict[str, Credential] = {}
        self._by_hash: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path == ":memory:" or not Path(self.path).exists():
            return
        try:
            raw = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for item in raw.get("credentials", []):
            try:
                cred = Credential(**item)
                self._creds[cred.cred_id] = cred
                self._by_hash[cred.token_hash] = cred.cred_id
            except (TypeError, KeyError):
                continue

    def _save(self) -> None:
        if self.path == ":memory:":
            return
        payload = {"credentials": [asdict(c) for c in self._creds.values()]}
        tmp = Path(self.path).with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- issuance -------------------------------------------------------------

    def issue(
        self,
        agent_id: str,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_uses: int = 1,
    ) -> str:
        """Issue a short-lived credential for ``agent_id``.

        Returns the raw token exactly once; only its hash is stored. ``max_uses``
        of 0 means "no use cap, TTL only"; any other value is a hard cap.
        """
        if not agent_id:
            raise ValueError("a credential must be bound to an agent_id")
        ttl = int(ttl_seconds)
        if ttl <= 0 or ttl > MAX_TTL_SECONDS:
            raise ValueError(f"ttl_seconds must be 1..{MAX_TTL_SECONDS}")
        if int(max_uses) < 0:
            raise ValueError("max_uses must be >= 0")

        token = "agtok_" + secrets.token_urlsafe(32)
        now = _utcnow()
        cred = Credential(
            cred_id="cred_" + uuid.uuid4().hex[:12],
            agent_id=agent_id,
            token_hash=_hash_token(token),
            issued_at=_iso(now),
            expires_at=_iso(now + timedelta(seconds=ttl)),
            max_uses=int(max_uses),
            uses=0,
        )
        with self._lock:
            self._creds[cred.cred_id] = cred
            self._by_hash[cred.token_hash] = cred.cred_id
            self._save()
        return token

    # -- verification ---------------------------------------------------------

    def verify(self, token: Optional[str], consume: bool = True) -> CredentialCheck:
        """Verify a token. Consumes one use on success by default (fail closed)."""
        if not token or not isinstance(token, str):
            return CredentialCheck(False, "no credential supplied")

        token_hash = _hash_token(token)
        with self._lock:
            cred_id = self._by_hash.get(token_hash)
            cred = self._creds.get(cred_id) if cred_id else None
            if cred is None:
                return CredentialCheck(False, "unknown credential")
            # Constant-time compare so a hash lookup cannot be probed by timing.
            if not hmac.compare_digest(cred.token_hash, token_hash):
                return CredentialCheck(False, "credential mismatch")
            if cred.revoked:
                return CredentialCheck(False, "credential revoked", cred.agent_id)
            if _utcnow() >= datetime.fromisoformat(cred.expires_at):
                return CredentialCheck(False, "credential expired", cred.agent_id)
            if cred.max_uses and cred.uses >= cred.max_uses:
                return CredentialCheck(False, "credential exhausted", cred.agent_id)
            if consume:
                cred.uses += 1
                self._save()
            return CredentialCheck(True, "credential valid", cred.agent_id)

    # -- revocation -----------------------------------------------------------

    def revoke(self, cred_id: str) -> bool:
        with self._lock:
            cred = self._creds.get(cred_id)
            if cred is None:
                return False
            cred.revoked = True
            self._save()
            return True

    def revoke_for_agent(self, agent_id: str) -> int:
        """Revoke every credential belonging to ``agent_id``. Returns the count."""
        count = 0
        with self._lock:
            for cred in self._creds.values():
                if cred.agent_id == agent_id and not cred.revoked:
                    cred.revoked = True
                    count += 1
            if count:
                self._save()
        return count

    # -- reads ----------------------------------------------------------------

    def list_for_agent(self, agent_id: str) -> List[Dict[str, Any]]:
        """Serialised credentials for an agent - hashes only, never tokens."""
        with self._lock:
            return [c.to_dict() for c in self._creds.values() if c.agent_id == agent_id]


_default: Optional[CredentialStore] = None


def get_credential_store() -> CredentialStore:
    """Process-wide credential store (durable unless GLUTEN_CRED_DB overrides)."""
    global _default
    if _default is None:
        import os

        _default = CredentialStore(os.environ.get("GLUTEN_CRED_DB"))
    return _default
