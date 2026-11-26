"""Scoped, single-use approval for running pasted code.

A fenced code block in a message is data, not an instruction. A pasted report
can carry one by accident, and a prompt-injected page can carry one on purpose,
so "the model noticed code" must never be enough to execute it - not even when
the caller is the owner.

The flow is therefore two steps:

1. ``request(user_id, code)`` parks the exact block and returns an id. Nothing
   runs. The user is told the id.
2. ``claim(user_id, request_id, code)`` is the explicit, scoped authorisation:
   it verifies the id belongs to that user, has not expired, has not been used,
   and that the code about to run is byte-identical to the code that was parked.
   It then marks the request used and returns it.

State lives in a JSON file (``GLUTEN_CODE_REQUESTS``, default
``data/gluten_code_requests.json``) so an approval survives the request that
created it, is auditable afterwards, and cannot be replayed after a restart.
The file is written atomically and readable only by the process owner.

Two storage rules keep the parked text from becoming a leak of its own:

* credential-shaped code is refused at ``request()`` (the same scanner the
  memory store uses), because a pasted block often contains the very key the
  user is debugging;
* ``claim()`` deletes the code from disk and keeps only its hash, so a used
  approval never leaves the source behind. Expired and consumed entries are
  pruned by ``cleanup()`` and on every write.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DEFAULT_PATH = "data/gluten_code_requests.json"


# The memory scanner covers the common vendors; these two also catch the
# multi-segment forms (``sk-proj-...``) and a key in a query string
# (``?key=AIza...``), which is how a key usually appears in pasted code.
_EXTRA_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"(?i)\b(key|token|secret|password|passwd)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"),
)


def _contains_credential(text: str) -> bool:
    from genesis_protocol.agentic.memory_safety import looks_like_secret

    if looks_like_secret(text):
        return True
    return any(pattern.search(text or "") for pattern in _EXTRA_SECRET_PATTERNS)


class CodeConsentError(RuntimeError):
    """Raised when a block cannot be parked (the reason never repeats the code)."""

DEFAULT_TTL_SECONDS = 900
MAX_KEPT_REQUESTS = 50


def _digest(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8", "replace")).hexdigest()


@dataclass
class CodeRequest:
    """One parked block of code awaiting an explicit approval."""

    request_id: str
    user_id: int
    code: str
    code_sha256: str
    created_at: float
    expires_at: float
    consumed_at: Optional[float] = None

    def is_expired(self, now: Optional[float] = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    @property
    def consumed(self) -> bool:
        return self.consumed_at is not None


class CodeConsentStore:
    """Park code, then release it once, for one user, for one exact block."""

    def __init__(self, path: Optional[str] = None,
                 ttl_seconds: float = DEFAULT_TTL_SECONDS):
        self.path = Path(path or os.environ.get("GLUTEN_CODE_REQUESTS", DEFAULT_PATH))
        self.ttl_seconds = ttl_seconds

    # -- storage -----------------------------------------------------------
    def _load(self) -> Dict[str, dict]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
        requests = data.get("requests") if isinstance(data, dict) else None
        return requests if isinstance(requests, dict) else {}

    def _save(self, requests: Dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A consumed entry keeps its hash (so a replay is reported as "already
        # used") but its code was blanked by claim(). Bounded by count here;
        # ``cleanup()`` drops expired and consumed entries.
        ordered = sorted(requests.items(),
                         key=lambda item: item[1].get("created_at", 0),
                         reverse=True)[:MAX_KEPT_REQUESTS]
        payload = {"requests": dict(ordered)}
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    @staticmethod
    def _to_request(entry: dict) -> Optional[CodeRequest]:
        try:
            return CodeRequest(
                request_id=entry["request_id"],
                user_id=int(entry["user_id"]),
                code=entry["code"],
                code_sha256=entry["code_sha256"],
                created_at=float(entry["created_at"]),
                expires_at=float(entry["expires_at"]),
                consumed_at=(float(entry["consumed_at"])
                             if entry.get("consumed_at") is not None else None),
            )
        except (KeyError, TypeError, ValueError):
            return None

    # -- public API --------------------------------------------------------
    def request(self, user_id: int, code: str) -> CodeRequest:
        """Park ``code`` for ``user_id``. Nothing is executed.

        Raises ``CodeConsentError`` for empty code and for credential-shaped
        code: the parked text is written to disk, so it must not be a secret.
        """
        if not (code or "").strip():
            raise CodeConsentError("no code to approve")
        if _contains_credential(code):
            raise CodeConsentError(
                "the block looks like it contains a credential; remove the secret "
                "and paste only the code"
            )

        self.cleanup()
        now = time.time()
        request = CodeRequest(
            request_id=secrets.token_hex(8),
            user_id=int(user_id),
            code=code,
            code_sha256=_digest(code),
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        requests = self._load()
        requests[request.request_id] = asdict(request)
        self._save(requests)
        return request

    def get(self, user_id: int, request_id: str) -> Optional[CodeRequest]:
        """Read a pending request without consuming it."""
        entry = self._load().get(request_id or "")
        request = self._to_request(entry) if entry else None
        if request is None or request.user_id != int(user_id):
            return None
        return request

    def claim(self, user_id: int, request_id: str,
              code: Optional[str] = None) -> Tuple[Optional[CodeRequest], str]:
        """Consume one approval. Returns ``(request, reason)``; request is None on refusal."""
        requests = self._load()
        entry = requests.get(request_id or "")
        request = self._to_request(entry) if entry else None
        if request is None:
            return None, "unknown approval id"
        if request.user_id != int(user_id):
            return None, "approval belongs to another user"
        if request.consumed:
            return None, "approval already used"
        if request.is_expired():
            return None, "approval expired"
        if code is not None and _digest(code) != request.code_sha256:
            return None, "approval does not match this code"

        request.consumed_at = time.time()
        stored = asdict(request)
        # The approval is spent; the source is not needed any more. Keep the
        # hash for audit, drop the text so it does not sit on disk.
        stored["code"] = ""
        requests[request.request_id] = stored
        self._save(requests)
        return request, "approved"

    def cleanup(self) -> int:
        """Drop expired and consumed entries. Returns how many were removed."""
        now = time.time()
        requests = self._load()
        keep = {}
        for request_id, entry in requests.items():
            request = self._to_request(entry)
            if request is None or request.consumed or request.is_expired(now):
                continue
            keep[request_id] = entry
        removed = len(requests) - len(keep)
        if removed:
            self._save(keep)
        return removed

    def pending(self, user_id: int) -> List[CodeRequest]:
        """Unconsumed, unexpired requests for one user."""
        now = time.time()
        out = []
        for entry in self._load().values():
            request = self._to_request(entry)
            if (request and request.user_id == int(user_id)
                    and not request.consumed and not request.is_expired(now)):
                out.append(request)
        return sorted(out, key=lambda r: r.created_at, reverse=True)


_default: Optional[CodeConsentStore] = None


def get_code_consent() -> CodeConsentStore:
    global _default
    if _default is None:
        _default = CodeConsentStore()
    return _default
